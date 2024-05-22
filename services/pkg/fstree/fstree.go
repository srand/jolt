package fstree

import (
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

	var magic uint16
	err := binary.Read(reader, binary.LittleEndian, &magic)
	if err != nil {
		return nil, err
	}
	if magic != TreeMagic {
		return nil, fmt.Errorf("invalid magic number: %x", magic)
	}

	var version uint16
	err = binary.Read(reader, binary.LittleEndian, &version)
	if err != nil {
		return nil, err
	}
	if version != TreeVersion {
		return nil, fmt.Errorf("invalid version: %d", version)
	}

	tree := NewTree(InodeType_Directory)

	for {
		// Read the path.
		var pathLength uint64
		err = binary.Read(reader, binary.LittleEndian, &pathLength)
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}
		if pathLength == 0 {
			break
		}

		path := make([]byte, pathLength)
		_, err = reader.Read(path)
		if err != nil {
			return nil, err
		}

		// Read the digest.
		var digestLength uint64
		err = binary.Read(reader, binary.LittleEndian, &digestLength)
		if err != nil {
			return nil, err
		}

		digest := make([]byte, digestLength)
		_, err = reader.Read(digest)
		if err != nil {
			return nil, err
		}

		// Read the status.
		var status uint32
		err = binary.Read(reader, binary.LittleEndian, &status)
		if err != nil {
			return nil, err
		}

		// Read the target if the inode is a symlink.
		if (status & InodeType_Symlink) != 0 {
			var targetLength uint64
			err = binary.Read(reader, binary.LittleEndian, &targetLength)
			if err != nil {
				return nil, err
			}

			target := make([]byte, targetLength)
			_, err = reader.Read(target)
			if err != nil {
				return nil, err
			}
		}

		tree.AddChild(NewInode(status, string(digest)))
	}

	return tree, nil
}
