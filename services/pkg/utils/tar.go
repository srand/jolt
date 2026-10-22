package utils

import (
	"archive/tar"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"time"
)

// Untar extracts an archive into dir. Entries, and the targets of links, must
// stay within dir. All files are created through an os.Root, so that a link
// from an earlier entry cannot redirect a later entry outside of dir.
func Untar(r io.Reader, dir string) (err error) {
	t0 := time.Now()
	madeDir := map[string]bool{}

	root, err := os.OpenRoot(dir)
	if err != nil {
		return err
	}
	defer root.Close()

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
		if !filepath.IsLocal(rel) {
			return fmt.Errorf("Archive entry %s is outside of the destination directory", f.Name)
		}

		fi := f.FileInfo()
		mode := fi.Mode()
		switch f.Typeflag {
		case tar.TypeReg:
			dir := filepath.Dir(rel)
			if !madeDir[dir] {
				if err := root.MkdirAll(dir, 0755); err != nil {
					return err
				}
				madeDir[dir] = true
			}
			wf, err := root.OpenFile(rel, os.O_RDWR|os.O_CREATE|os.O_TRUNC, mode.Perm())
			if err != nil {
				return err
			}
			n, err := io.Copy(wf, tr)
			if closeErr := wf.Close(); closeErr != nil && err == nil {
				err = closeErr
			}
			if err != nil {
				return fmt.Errorf("Error writing to %s: %v", f.Name, err)
			}
			if n != f.Size {
				return fmt.Errorf("Only wrote %d bytes to %s; expected %d", n, f.Name, f.Size)
			}
			modTime := f.ModTime
			if modTime.After(t0) {
				modTime = t0
			}
		case tar.TypeDir:
			if err := root.MkdirAll(rel, mode.Perm()); err != nil {
				return err
			}
			madeDir[rel] = true
		case tar.TypeSymlink:
			target := filepath.FromSlash(f.Linkname)
			if !isLocalSymlink(root, rel, target) {
				return fmt.Errorf("Archive entry %s links outside of the destination directory: %s", f.Name, f.Linkname)
			}
			if err := root.Symlink(target, rel); err != nil {
				return err
			}
		case tar.TypeLink:
			target := filepath.FromSlash(f.Linkname)
			if !filepath.IsLocal(target) {
				return fmt.Errorf("Archive entry %s links outside of the destination directory: %s", f.Name, f.Linkname)
			}
			if err := root.Link(target, rel); err != nil {
				return err
			}
		default:
			return fmt.Errorf("Archive entry %s contained unsupported file type %v", f.Name, mode)
		}
	}
	return nil
}

// Checks that a symlink at rel pointing to target resolves within the root.
// The check is lexical, so it only holds if the path of the link matches its
// location on disk, which it does not if a directory leading up to it is
// itself a symlink, and if the target cannot move up again after moving down
// through another symlink, which it can if ".." follows a name.
func isLocalSymlink(root *os.Root, rel, target string) bool {
	if filepath.IsAbs(target) || filepath.Clean(target) != target {
		return false
	}
	if !filepath.IsLocal(filepath.Join(filepath.Dir(rel), target)) {
		return false
	}
	for dir := filepath.Dir(rel); dir != "."; dir = filepath.Dir(dir) {
		if info, err := root.Lstat(dir); err == nil && info.Mode()&os.ModeSymlink != 0 {
			return false
		}
	}
	return true
}
