package cache

import (
	context "context"
	"io"
	sync "sync"

	"github.com/srand/jolt/scheduler/pkg/fstree"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"golang.org/x/sync/errgroup"
	codes "google.golang.org/grpc/codes"
	status "google.golang.org/grpc/status"
)

// Generate protocol buffer code and gRPC stubs.
//go:generate protoc -I. --go_out=../.. --go-grpc_out=../.. cache.proto

// Maximum number of subtrees that a single HasTree request checks at once.
// Each check opens a tree object and looks up its children, so an unbounded
// number would open as many files as the tree has directories.
var hasTreeConcurrency = 64

// Set of digests that a HasTree request has already checked. Identical
// directories and files occur many times in a workspace, but each only needs
// to be checked, and reported missing, once.
//
// Every subtree check adds to the set concurrently, so it is split into shards
// by the first byte of the digest, each with its own lock.
type digestSet struct {
	shards [256]struct {
		sync.Mutex
		digests map[utils.Digest]struct{}
	}
}

// Adds the digest to the set and returns true if it was not already present.
func (s *digestSet) add(digest utils.Digest) bool {
	shard := &s.shards[shardOf(digest.Hex())]
	shard.Lock()
	defer shard.Unlock()

	if shard.digests == nil {
		shard.digests = make(map[utils.Digest]struct{})
	}
	if _, found := shard.digests[digest]; found {
		return false
	}
	shard.digests[digest] = struct{}{}
	return true
}

// Returns the value of the first byte of a lower case hex string.
func shardOf(hex string) uint8 {
	nibble := func(c byte) uint8 {
		if c >= 'a' {
			return c - 'a' + 10
		}
		return c - '0'
	}
	if len(hex) < 2 {
		return 0
	}
	return nibble(hex[0])<<4 | nibble(hex[1])
}

type cacheService struct {
	UnimplementedCacheServiceServer
	cache Cache
}

func NewCacheService(cache Cache) CacheServiceServer {
	return &cacheService{
		cache: cache,
	}
}

// HasObject returns a list of blobs that are either missing or present in the cache.
func (svc *cacheService) HasObject(ctx context.Context, req *HasObjectRequest) (*HasObjectResponse, error) {
	presence := make([]bool, 0, len(req.Digest))
	for _, digest := range req.Digest {
		d, err := utils.ParseDigest(digest)
		if err != nil {
			return nil, status.Errorf(codes.InvalidArgument, "invalid digest: %v", err)
		}

		present := svc.cache.HasObject(d) != nil
		presence = append(presence, present)
	}

	return &HasObjectResponse{
		Present: presence,
	}, nil
}

func (svc *cacheService) checkTree(ctx context.Context, server CacheService_HasTreeServer, m *sync.Mutex, eg *errgroup.Group, seen *digestSet, digest utils.Digest) error {
	var tree *fstree.Tree

	// Stop walking once the client is gone or another subtree has failed.
	if err := ctx.Err(); err != nil {
		return status.FromContextError(err).Err()
	}

	response := &HasTreeResponse{
		MissingTrees:   make([]string, 0),
		MissingObjects: make([]string, 0),
	}

	// Read the tree from the cache.
	reader, err := svc.cache.ReadObject(digest)
	if err != nil {
		response.MissingTrees = append(response.MissingTrees, digest.String())
		goto sendResponse
	}

	tree, err = fstree.ReadTree(reader)
	reader.Close()
	if err != nil {
		return status.Errorf(codes.Internal, "failed to read tree: %v: %v", digest.Hex(), err)
	}

	for _, child := range tree.Children {
		digest, err := utils.ParseDigest(child.Digest())

		switch child.Type() {
		case fstree.InodeType_Directory:
			if err != nil {
				return status.Errorf(codes.InvalidArgument, "invalid digest: %v", err)
			}

			if !seen.add(digest) {
				continue
			}

			// Check the subtree here if no slot is free. Waiting for one
			// would deadlock once every running check is waiting too.
			if !eg.TryGo(func() error {
				return svc.checkTree(ctx, server, m, eg, seen, digest)
			}) {
				if err := svc.checkTree(ctx, server, m, eg, seen, digest); err != nil {
					return err
				}
			}

		case fstree.InodeType_Symlink:
			// Skip symlinks.

		default:
			if err != nil {
				return status.Errorf(codes.InvalidArgument, "invalid digest: %v", err)
			}

			if !seen.add(digest) {
				continue
			}

			if info := svc.cache.HasObject(digest); info == nil {
				response.MissingObjects = append(response.MissingObjects, child.Digest())
			}
		}
	}

sendResponse:
	if len(response.MissingObjects) == 0 && len(response.MissingTrees) == 0 {
		return nil
	}

	m.Lock()
	defer m.Unlock()

	err = server.Send(response)
	if err != nil {
		return status.Errorf(codes.Internal, "failed to send response: %v", err)
	}

	return nil
}

func (svc *cacheService) HasTree(req *HasTreeRequest, server CacheService_HasTreeServer) error {
	eg, ctx := errgroup.WithContext(server.Context())
	eg.SetLimit(hasTreeConcurrency)
	trees := []utils.Digest{}
	m := sync.Mutex{}
	seen := &digestSet{}

	// For each digest in the list
	for _, digest := range req.Digest {
		d, err := utils.ParseDigest(digest)
		if err != nil {
			return status.Errorf(codes.InvalidArgument, "invalid digest: %v", err)
		}
		if seen.add(d) {
			trees = append(trees, d)
		}
	}

	for i := range trees {
		digest := trees[i]
		if !eg.TryGo(func() error {
			return svc.checkTree(ctx, server, &m, eg, seen, digest)
		}) {
			if err := svc.checkTree(ctx, server, &m, eg, seen, digest); err != nil {
				eg.Wait()
				return err
			}
		}
	}

	if err := eg.Wait(); err != nil {
		return err
	}

	return nil
}

// ReadObject reads a blob from the cache.
func (svc *cacheService) ReadObject(req *ReadObjectRequest, srv CacheService_ReadObjectServer) error {
	digest, err := utils.ParseDigest(req.Digest)
	if err != nil {
		return status.Errorf(codes.InvalidArgument, "invalid digest: %v", err)
	}

	reader, err := svc.cache.ReadObject(digest)
	if err != nil {
		return status.Errorf(codes.Internal, "failed to read blob %s: %v", digest, err)
	}
	defer reader.Close()

	buf := make([]byte, 0x10000)
	for {
		n, err := reader.Read(buf)
		if n > 0 {
			if err := srv.Send(&ReadObjectResponse{
				Data: buf[:n],
			}); err != nil {
				return status.Errorf(codes.Internal, "failed to send response: %v", err)
			}
		}
		if err != nil {
			if err == io.EOF {
				log.Debug("GET object", digest)
				return nil
			}
			return status.Errorf(codes.Internal, "failed to read blob: %v", err)
		}
	}
}

// WriteObject writes a blob to the cache.
func (x *cacheService) WriteObject(srv CacheService_WriteObjectServer) error {
	var writer WriteCloseDiscarder
	var digest utils.Digest

	for {
		req, err := srv.Recv()
		if err != nil {
			if err == io.EOF {
				if writer != nil {
					if err := writer.Close(); err != nil {
						log.Debug("failed to close blob", err)
						return status.Errorf(codes.Internal, "failed to close blob: %v", err)
					}
					log.Debug("PUT object", digest)
					return nil
				}
				return nil
			}
			if writer != nil {
				writer.Discard()
			}
			log.Debug("failed to receive request", err)
			return status.Errorf(codes.Internal, "failed to receive request: %v", err)
		}

		if writer == nil {
			digest, err = utils.ParseDigest(req.Digest)
			if err != nil {
				log.Debug("invalid digest", digest, err)
				return status.Errorf(codes.InvalidArgument, "invalid digest: %v", err)
			}

			if info := x.cache.HasObject(digest); info != nil {
				log.Debug("object already in cache", digest)
				return status.Errorf(codes.AlreadyExists, "object already in cache: %v", digest)
			}

			writer, err = x.cache.WriteObject(digest)
			if err != nil {
				log.Debug("failed to create blob", err)
				return status.Errorf(codes.Internal, "failed to write blob: %v", err)
			}
		}

		if _, err := writer.Write([]byte(req.Data)); err != nil {
			if writer != nil {
				writer.Discard()
			}
			log.Debug("failed to write blob", err)
			return status.Errorf(codes.Internal, "failed to write blob: %v", err)
		}
	}
}
