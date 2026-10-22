package fstree

import (
	"bytes"
	"encoding/binary"
	"io"
	"testing"
	"testing/iotest"

	"github.com/stretchr/testify/assert"
)

type testChild struct {
	name   string
	digest string
	status uint32
	target string
}

// Serialize a tree object in the format written by fstree.
func encodeTree(children []testChild) []byte {
	var buf bytes.Buffer
	binary.Write(&buf, binary.LittleEndian, uint16(TreeMagic))
	binary.Write(&buf, binary.LittleEndian, uint16(TreeVersion))
	for _, c := range children {
		binary.Write(&buf, binary.LittleEndian, uint64(len(c.name)))
		buf.WriteString(c.name)
		binary.Write(&buf, binary.LittleEndian, uint64(len(c.digest)))
		buf.WriteString(c.digest)
		binary.Write(&buf, binary.LittleEndian, c.status)
		if c.status&InodeType_Symlink != 0 {
			binary.Write(&buf, binary.LittleEndian, uint64(len(c.target)))
			buf.WriteString(c.target)
		}
	}
	return buf.Bytes()
}

var testChildren = []testChild{
	{name: "dir", digest: "blake3:" + string(bytes.Repeat([]byte("a"), 64)), status: InodeType_Directory | 0755},
	{name: "file.txt", digest: "blake3:" + string(bytes.Repeat([]byte("b"), 64)), status: InodeType_Regular | 0644},
	{name: "link", digest: "", status: InodeType_Symlink | 0777, target: "file.txt"},
}

func assertTree(t *testing.T, tree *Tree) {
	if !assert.Len(t, tree.Children, len(testChildren)) {
		return
	}
	for i, c := range testChildren {
		assert.Equal(t, c.digest, tree.Children[i].Digest())
		assert.Equal(t, int(c.status&0xff000000), tree.Children[i].Type())
	}
}

func TestReadTree(t *testing.T) {
	tree, err := ReadTree(bytes.NewReader(encodeTree(testChildren)))
	assert.NoError(t, err)
	assertTree(t, tree)
}

func TestReadTreeShortReads(t *testing.T) {
	// A reader may return fewer bytes than requested, as a file or network
	// stream does at buffer boundaries. Fields must still be read in full.
	tree, err := ReadTree(iotest.OneByteReader(bytes.NewReader(encodeTree(testChildren))))
	assert.NoError(t, err)
	assertTree(t, tree)
}

func TestReadTreeTruncated(t *testing.T) {
	data := encodeTree(testChildren)
	_, err := ReadTree(bytes.NewReader(data[:len(data)-3]))
	assert.Error(t, err)
}

func TestReadTreeOversizedField(t *testing.T) {
	// Length fields come from the object and must not be trusted to size
	// allocations, or a crafted object could exhaust the server's memory.
	var buf bytes.Buffer
	binary.Write(&buf, binary.LittleEndian, uint16(TreeMagic))
	binary.Write(&buf, binary.LittleEndian, uint16(TreeVersion))
	binary.Write(&buf, binary.LittleEndian, uint64(1)<<40)
	_, err := ReadTree(&buf)
	assert.Error(t, err)
}

type countingReader struct {
	reader io.Reader
	reads  int
}

func (r *countingReader) Read(p []byte) (int, error) {
	r.reads++
	return r.reader.Read(p)
}

func TestReadTreeBuffersReads(t *testing.T) {
	// Tree objects are read straight from files. Each field must not cost
	// a read of its own on the underlying reader, i.e. a system call.
	reader := &countingReader{reader: bytes.NewReader(encodeTree(testChildren))}
	tree, err := ReadTree(reader)
	assert.NoError(t, err)
	assertTree(t, tree)
	assert.LessOrEqual(t, reader.reads, 2)
}
