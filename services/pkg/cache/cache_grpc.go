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

func (svc *cacheService) checkTree(server CacheService_HasTreeServer, m *sync.Mutex, eg *errgroup.Group, digest utils.Digest) error {
	var tree *fstree.Tree

	response := &HasTreeResponse{
		MissingTrees:   make([]string, 0),
		MissingObjects: make([]string, 0),
	}

	// Read the tree from the cache.
	reader, err := svc.cache.ReadObject(digest)
	if err != nil {
		response.MissingTrees = append(response.MissingTrees, digest.Hex())
		goto sendResponse
	}

	tree, err = fstree.ReadTree(reader)
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

			eg.Go(func() error {
				return svc.checkTree(server, m, eg, digest)
			})

		case fstree.InodeType_Symlink:
			// Skip symlinks.

		default:
			if err != nil {
				return status.Errorf(codes.InvalidArgument, "invalid digest: %v", err)
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
	eg := errgroup.Group{}
	trees := []utils.Digest{}
	m := sync.Mutex{}

	// For each digest in the list
	for _, digest := range req.Digest {
		d, err := utils.ParseDigest(digest)
		if err != nil {
			return status.Errorf(codes.InvalidArgument, "invalid digest: %v", err)
		}
		trees = append(trees, d)
	}

	for i := range trees {
		digest := trees[i]
		eg.Go(func() error {
			return svc.checkTree(server, &m, &eg, digest)
		})
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
