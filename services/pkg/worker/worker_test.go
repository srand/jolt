package worker

import (
	"path/filepath"
	"testing"

	"github.com/srand/jolt/scheduler/pkg/protocol"
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

func TestCheckoutArgsIgnorePatterns(t *testing.T) {
	w := &worker{
		config: &WorkerConfig{CacheDir: "/cache", CacheGrpcUri: "tcp://cache:9090", ThreadCount: 4},
	}

	// The checkout ignores what the client wrote the tree without
	workspace := &protocol.Workspace{
		Name:           "monorepo",
		Tree:           "blake3:1234",
		IgnorePatterns: []string{".git", "/build/"},
	}
	assert.Equal(t, []string{
		"fstree", "pull-checkout", "--cache", "/cache",
		"--ignore", ".joltignore",
		"--ignore-pattern", ".git", "--ignore-pattern", "/build/",
		"--permissions", "git",
		"--index", "/index", "--remote", "tcp://cache:9090", "--threads", "4",
		"--jobserver-path", "/jobserver",
		"blake3:1234", "monorepo",
	}, w.checkoutArgs(workspace, "/index", "/jobserver"))

	// Without patterns, from an older client, no --ignore-pattern options
	// are given
	workspace.IgnorePatterns = nil
	assert.Equal(t, []string{
		"fstree", "pull-checkout", "--cache", "/cache",
		"--ignore", ".joltignore",
		"--permissions", "git",
		"--index", "/index", "--remote", "tcp://cache:9090", "--threads", "4",
		"blake3:1234", "monorepo",
	}, w.checkoutArgs(workspace, "/index", ""))
}
