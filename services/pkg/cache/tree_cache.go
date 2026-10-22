package cache

import (
	"github.com/srand/jolt/scheduler/pkg/fstree"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

// Approximate memory used for each digest held by a parsed tree.
const parsedTreeDigestSize = 128

// The children of a tree object, parsed.
type parsedTree struct {
	digest  string
	trees   []utils.Digest
	objects []utils.Digest
}

func (t *parsedTree) Path() string {
	return t.digest
}

func (t *parsedTree) Size() int64 {
	return int64(1+len(t.trees)+len(t.objects)) * parsedTreeDigestSize
}

// Parses the children of a tree object. Symlinks are left out, as they are
// stored in the tree itself.
func parseTree(digest utils.Digest, tree *fstree.Tree) (*parsedTree, error) {
	parsed := &parsedTree{digest: digest.String()}

	for _, child := range tree.Children {
		if child.Type() == fstree.InodeType_Symlink {
			continue
		}

		childDigest, err := utils.ParseDigest(child.Digest())
		if err != nil {
			return nil, err
		}

		if child.Type() == fstree.InodeType_Directory {
			parsed.trees = append(parsed.trees, childDigest)
		} else {
			parsed.objects = append(parsed.objects, childDigest)
		}
	}

	return parsed, nil
}

// Parsed trees, kept so that HasTree need not read and parse the same tree
// objects for every push. Tree objects are named by their digest and never
// change, so a parsed tree is valid as long as its object is in the cache.
type treeCache struct {
	lru *utils.LRU[*parsedTree]
}

func newTreeCache(size int64) *treeCache {
	return &treeCache{
		lru: utils.NewLRU[*parsedTree](size, func(*parsedTree) bool { return true }),
	}
}

func (c *treeCache) get(digest utils.Digest) (*parsedTree, bool) {
	return c.lru.Get(digest.String())
}

func (c *treeCache) add(tree *parsedTree) {
	c.lru.Add(tree)
}
