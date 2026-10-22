package fstree

import (
	"bufio"
	"encoding/binary"
	"fmt"
	"io"
)

const (
	InodeType_Regular   = 1 << 24
	InodeType_Directory = 2 << 24
	InodeType_Symlink   = 4 << 24
)

const (
	TreeMagic   = 0x3eee
	TreeVersion = 1
)

// Upper bound for the length of a path, digest or symlink target in a tree
// object. Lengths are read from the object, which any client can upload, so
// they must be bounded before they are used to size an allocation.
const MaxFieldLength = 1 << 20

type Inode interface {
	Type() int
	Digest() string
}

type Node struct {
	status uint32
	digest string
}

func NewInode(status uint32, digest string) *Node {
	return &Node{
		status: status,
		digest: digest,
	}
}

func (i *Node) Type() int {
	return int(i.status & 0xff000000)
}

func (i *Node) Digest() string {
	return i.digest
}

type Tree struct {
	Node
	Children []Inode
}

func NewTree(status uint32) *Tree {
	return &Tree{
		Node: Node{
			status: status,
		},
		Children: make([]Inode, 0),
	}
}

func (t *Tree) AddChild(inode Inode) {
	t.Children = append(t.Children, inode)
}

func (t *Tree) Digest() string {
	return t.digest
}

func ReadTree(reader io.Reader) (*Tree, error) {
	// Deserialize the tree from the reader.

	// Format:
	// - Magic number (uint16)
	// - Version (uint16)
	// - Children:
	//   - Length of path (uint64)
	//   - Path (string)
	//   - Length of digest (uint64)
	//   - Digest (string)
	//   - Status (uint32
	//   - If status == Inode_Symlink:
	//     - Length of target (uint64)
	//     - Target (string)

	// Fields are only a few bytes each, so read through a buffer instead of
	// issuing a read on the underlying reader for every one of them.
	br := bufio.NewReader(reader)

	// Integers are decoded from a single scratch buffer, and digests read into
	// another, since binary.Read and fresh slices would allocate for every
	// field of every entry.
	var scratch [8]byte
	readUint := func(size int) (uint64, error) {
		if _, err := io.ReadFull(br, scratch[:size]); err != nil {
			return 0, err
		}
		switch size {
		case 2:
			return uint64(binary.LittleEndian.Uint16(scratch[:])), nil
		case 4:
			return uint64(binary.LittleEndian.Uint32(scratch[:])), nil
		default:
			return binary.LittleEndian.Uint64(scratch[:]), nil
		}
	}

	// Skips a field that is not needed, such as a path or symlink target.
	skip := func(length uint64) error {
		if _, err := br.Discard(int(length)); err != nil {
			if err == io.EOF {
				return io.ErrUnexpectedEOF
			}
			return err
		}
		return nil
	}

	magic, err := readUint(2)
	if err != nil {
		return nil, err
	}
	if magic != TreeMagic {
		return nil, fmt.Errorf("invalid magic number: %x", magic)
	}

	version, err := readUint(2)
	if err != nil {
		return nil, err
	}
	if version != TreeVersion {
		return nil, fmt.Errorf("invalid version: %d", version)
	}

	tree := NewTree(InodeType_Directory)
	var digest []byte

	for {
		// Read the path.
		pathLength, err := readUint(8)
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}
		if pathLength == 0 {
			break
		}

		if pathLength > MaxFieldLength {
			return nil, fmt.Errorf("path length out of range: %d", pathLength)
		}

		if err := skip(pathLength); err != nil {
			return nil, err
		}

		// Read the digest.
		digestLength, err := readUint(8)
		if err != nil {
			return nil, err
		}

		if digestLength > MaxFieldLength {
			return nil, fmt.Errorf("digest length out of range: %d", digestLength)
		}

		if uint64(cap(digest)) < digestLength {
			digest = make([]byte, digestLength)
		}
		digest = digest[:digestLength]
		if _, err := io.ReadFull(br, digest); err != nil {
			return nil, err
		}

		// Read the status.
		status64, err := readUint(4)
		if err != nil {
			return nil, err
		}
		status := uint32(status64)

		// Read the target if the inode is a symlink.
		if (status & InodeType_Symlink) != 0 {
			targetLength, err := readUint(8)
			if err != nil {
				return nil, err
			}

			if targetLength > MaxFieldLength {
				return nil, fmt.Errorf("target length out of range: %d", targetLength)
			}

			if err := skip(targetLength); err != nil {
				return nil, err
			}
		}

		tree.AddChild(NewInode(status, string(digest)))
	}

	return tree, nil
}
