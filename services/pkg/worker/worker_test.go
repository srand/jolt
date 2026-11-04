package worker

import (
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestWorkspaceIndexPathMatchesJolt(t *testing.T) {
	cache := t.TempDir()
	w := &worker{
		config: &WorkerConfig{CacheDir: cache},
		cwd:    "/vol/jolt-worker-default-v2-7d5645fc64-df4wh/ws",
	}

	// The index that Jolt wrote for this workspace in a worker pod
	index, err := w.workspaceIndexPath("monorepo")
	assert.NoError(t, err)
	assert.Equal(t, filepath.Join(cache, "indexes", "fc", "57375c36f4b1020c37cea144e13327e496315c930d357a8a12fc8859d2f1ae"), index)
	assert.DirExists(t, filepath.Dir(index))
}
