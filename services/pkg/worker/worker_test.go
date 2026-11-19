package worker

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestExecutorReceivesSubmitterTokenWithoutChangingWorkerEnvironment(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("test uses shell scripts")
	}
	t.Setenv("JOLT_SCHEDULER_TOKEN", "worker-token")
	for _, nix := range []bool{false, true} {
		for _, token := range []string{"submitter-token '$;", ""} {
			w := &worker{cwd: t.TempDir(), config: &WorkerConfig{Nix: nix}}
			bin := filepath.Join(w.cwd, "bin")
			require.NoError(t, os.MkdirAll(bin, 0700))
			t.Setenv("PATH", bin+string(os.PathListSeparator)+os.Getenv("PATH"))
			output := filepath.Join(w.cwd, "token")
			t.Setenv("TOKEN_OUTPUT", output)
			require.NoError(t, os.WriteFile(filepath.Join(bin, "jolt"), []byte("#!/bin/sh\nprintf '%s' \"${JOLT_SCHEDULER_TOKEN-unset}\" > \"$TOKEN_OUTPUT\"\n"), 0700))
			activate := w.activateVEnvPath("client")
			require.NoError(t, os.MkdirAll(filepath.Dir(activate), 0700))
			require.NoError(t, os.WriteFile(activate, nil, 0600))
			if nix {
				require.NoError(t, os.MkdirAll(filepath.Join(w.cwd, "workspace"), 0700))
				require.NoError(t, os.WriteFile(filepath.Join(w.cwd, "workspace", "shell.nix"), nil, 0600))
				script := []byte("#!/bin/sh\ncase \" $* \" in *' --keep JOLT_SCHEDULER_TOKEN '*) exec jolt;; *) exit 1;; esac\n")
				for _, name := range []string{"nix-shell", "cached-nix-shell"} {
					require.NoError(t, os.WriteFile(filepath.Join(bin, name), script, 0700))
				}
			}
			done, _, err := w.startExecutor("client", &protocol.Client{Version: "0.9.242", Nix: nix}, &protocol.Workspace{Name: "workspace"}, "worker", "build", "request", token)
			require.NoError(t, err)
			require.NoError(t, <-done)
			value, err := os.ReadFile(output)
			require.NoError(t, err)
			if token == "" {
				assert.Equal(t, "unset", string(value))
			} else {
				assert.Equal(t, token, string(value))
			}
			assert.Equal(t, "worker-token", os.Getenv("JOLT_SCHEDULER_TOKEN"))
		}
	}
}

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
