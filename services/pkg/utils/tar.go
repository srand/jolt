//go:build !windows

package utils

import (
	"archive/tar"
	"fmt"
	"io"
	"os"
	"path"
	"path/filepath"
	"time"
)

func Untar(r io.Reader, dir string) (err error) {
	t0 := time.Now()
	madeDir := map[string]bool{}

	tr := tar.NewReader(r)

	for {
		f, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return fmt.Errorf("Archive read error: %v", err)
		}

		rel := filepath.FromSlash(f.Name)
		abs := filepath.Join(dir, rel)

		fi := f.FileInfo()
		mode := fi.Mode()
		switch f.Typeflag {
		case tar.TypeReg:
			dir := filepath.Dir(abs)
			if !madeDir[dir] {
				if err := os.MkdirAll(filepath.Dir(abs), 0755); err != nil {
					return err
				}
				madeDir[dir] = true
			}
			wf, err := os.OpenFile(abs, os.O_RDWR|os.O_CREATE|os.O_TRUNC, mode.Perm())
			if err != nil {
				return err
			}
			n, err := io.Copy(wf, tr)
			if closeErr := wf.Close(); closeErr != nil && err == nil {
				err = closeErr
			}
			if err != nil {
				return fmt.Errorf("Error writing to %s: %v", abs, err)
			}
			if n != f.Size {
				return fmt.Errorf("Only wrote %d bytes to %s; expected %d", n, abs, f.Size)
			}
			modTime := f.ModTime
			if modTime.After(t0) {
				modTime = t0
			}
		case tar.TypeDir:
			if err := os.MkdirAll(abs, mode.Perm()); err != nil {
				return err
			}
			madeDir[abs] = true
		case tar.TypeSymlink:
			if err := os.Symlink(f.Linkname, abs); err != nil {
				return err
			}
		case tar.TypeLink:
			abslinkname := path.Join(dir, f.Linkname)
			if err := os.Link(abslinkname, abs); err != nil {
				return err
			}
		default:
			return fmt.Errorf("Archive entry %s contained unsupported file type %v", f.Name, mode)
		}
	}
	return nil
}
