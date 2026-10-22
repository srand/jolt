package utils

import (
	"archive/tar"
	"bytes"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
)

type tarEntry struct {
	name     string
	typeflag byte
	linkname string
	content  string
}

func makeTar(t *testing.T, entries ...tarEntry) *bytes.Buffer {
	t.Helper()

	buf := &bytes.Buffer{}
	tw := tar.NewWriter(buf)
	for _, e := range entries {
		header := &tar.Header{
			Name:     e.name,
			Typeflag: e.typeflag,
			Linkname: e.linkname,
			Mode:     0644,
			Size:     int64(len(e.content)),
		}
		if e.typeflag == tar.TypeDir {
			header.Mode = 0755
		}
		assert.NoError(t, tw.WriteHeader(header))
		if e.content != "" {
			_, err := tw.Write([]byte(e.content))
			assert.NoError(t, err)
		}
	}
	assert.NoError(t, tw.Close())
	return buf
}

// Returns a directory to extract into, inside a parent directory that a
// malicious archive would try to write to.
func untarDir(t *testing.T) (string, string) {
	t.Helper()

	parent := t.TempDir()
	dir := filepath.Join(parent, "dest")
	assert.NoError(t, os.Mkdir(dir, 0755))
	return parent, dir
}

func TestUntar(t *testing.T) {
	_, dir := untarDir(t)

	archive := makeTar(t,
		tarEntry{name: "pkg/", typeflag: tar.TypeDir},
		tarEntry{name: "pkg/file.txt", typeflag: tar.TypeReg, content: "hello"},
		tarEntry{name: "pkg/sub/", typeflag: tar.TypeDir},
		tarEntry{name: "pkg/sub/link", typeflag: tar.TypeSymlink, linkname: "../file.txt"},
		tarEntry{name: "hardlink", typeflag: tar.TypeLink, linkname: "pkg/file.txt"},
	)
	assert.NoError(t, Untar(archive, dir))

	for _, name := range []string{"pkg/file.txt", "pkg/sub/link", "hardlink"} {
		data, err := os.ReadFile(filepath.Join(dir, name))
		assert.NoError(t, err, name)
		assert.Equal(t, "hello", string(data), name)
	}
}

func TestUntarRejectsEntriesOutsideDirectory(t *testing.T) {
	tests := map[string][]tarEntry{
		"parent":        {{name: "../evil", typeflag: tar.TypeReg, content: "x"}},
		"nested parent": {{name: "pkg/../../evil", typeflag: tar.TypeReg, content: "x"}},
		"absolute":      {{name: "/evil", typeflag: tar.TypeReg, content: "x"}},
		"directory":     {{name: "../newdir/", typeflag: tar.TypeDir}},
		"symlink to parent": {
			{name: "link", typeflag: tar.TypeSymlink, linkname: ".."},
		},
		"symlink to absolute path": {
			{name: "link", typeflag: tar.TypeSymlink, linkname: "/etc"},
		},
		"symlink through symlink": {
			{name: "d", typeflag: tar.TypeSymlink, linkname: "."},
			{name: "d/link", typeflag: tar.TypeSymlink, linkname: ".."},
		},
		"symlink target through symlink": {
			{name: "d", typeflag: tar.TypeSymlink, linkname: "."},
			{name: "link", typeflag: tar.TypeSymlink, linkname: "d/.."},
		},
		// The name is local, but on disk pkg/up/.. is the parent of the
		// destination. Only os.Root can catch this.
		"write through symlink": {
			{name: "pkg/", typeflag: tar.TypeDir},
			{name: "pkg/up", typeflag: tar.TypeSymlink, linkname: ".."},
			{name: "pkg/up/../evil", typeflag: tar.TypeReg, content: "x"},
		},
		"hard link": {
			{name: "link", typeflag: tar.TypeLink, linkname: "../evil"},
		},
	}

	for name, entries := range tests {
		t.Run(name, func(t *testing.T) {
			parent, dir := untarDir(t)
			assert.NoError(t, os.WriteFile(filepath.Join(parent, "evil"), []byte("original"), 0644))

			assert.Error(t, Untar(makeTar(t, entries...), dir))

			// Nothing outside of the destination may have been touched, and
			// no link from inside may lead out of it.
			data, err := os.ReadFile(filepath.Join(parent, "evil"))
			assert.NoError(t, err)
			assert.Equal(t, "original", string(data))
			siblings, err := os.ReadDir(parent)
			assert.NoError(t, err)
			assert.Len(t, siblings, 2)

			filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
				if err == nil && info.Mode()&os.ModeSymlink != 0 {
					resolved, err := filepath.EvalSymlinks(path)
					if err == nil {
						rel, err := filepath.Rel(dir, resolved)
						assert.NoError(t, err)
						assert.True(t, filepath.IsLocal(rel), "%s resolves to %s", path, resolved)
					}
				}
				return nil
			})
		})
	}
}
