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

func TestReadTreeWireFormat(t *testing.T) {
	// Tree objects are written by the fstree tool, so the format is spelled
	// out byte by byte rather than encoded with the constants of this package.
	data := []byte{
		0xee, 0x3e, // magic
		0x01, 0x00, // version
		// directory "d" with digest "x"
		0x01, 0, 0, 0, 0, 0, 0, 0, 'd',
		0x01, 0, 0, 0, 0, 0, 0, 0, 'x',
		0xed, 0x01, 0x00, 0x02,
		// file "f" with digest "y"
		0x01, 0, 0, 0, 0, 0, 0, 0, 'f',
		0x01, 0, 0, 0, 0, 0, 0, 0, 'y',
		0xa4, 0x01, 0x00, 0x01,
		// symlink "l" to "f"
		0x01, 0, 0, 0, 0, 0, 0, 0, 'l',
		0x00, 0, 0, 0, 0, 0, 0, 0,
		0xff, 0x01, 0x00, 0x04,
		0x01, 0, 0, 0, 0, 0, 0, 0, 'f',
	}
	tree, err := ReadTree(bytes.NewReader(data))
	if !assert.NoError(t, err) || !assert.Len(t, tree.Children, 3) {
		return
	}
	assert.Equal(t, 0x02000000, tree.Children[0].Type())
	assert.Equal(t, InodeType_Directory, tree.Children[0].Type())
	assert.Equal(t, "x", tree.Children[0].Digest())
	assert.Equal(t, 0x01000000, tree.Children[1].Type())
	assert.Equal(t, InodeType_Regular, tree.Children[1].Type())
	assert.Equal(t, "y", tree.Children[1].Digest())
	assert.Equal(t, 0x04000000, tree.Children[2].Type())
	assert.Equal(t, InodeType_Symlink, tree.Children[2].Type())
	assert.Equal(t, "", tree.Children[2].Digest())
	assert.Equal(t, InodeType_Directory, tree.Type())
}

func TestReadTreeRejectsOtherMagicAndVersion(t *testing.T) {
	for _, header := range [][]byte{
		{0xed, 0x3e, 0x01, 0x00},
		{0xef, 0x3e, 0x01, 0x00},
		{0xee, 0x3e, 0x00, 0x00},
		{0xee, 0x3e, 0x02, 0x00},
	} {
		_, err := ReadTree(bytes.NewReader(header))
		assert.Error(t, err, "%x", header)
	}

	tree, err := ReadTree(bytes.NewReader([]byte{0xee, 0x3e, 0x01, 0x00}))
	assert.NoError(t, err)
	assert.Empty(t, tree.Children)
}

func TestReadTreeStopsAtEmptyPath(t *testing.T) {
	// A zero path length ends the list of children, whatever follows.
	data := encodeTree(testChildren[:1])
	data = binary.LittleEndian.AppendUint64(data, 0)
	data = append(data, "garbage"...)
	tree, err := ReadTree(bytes.NewReader(data))
	assert.NoError(t, err)
	assert.Len(t, tree.Children, 1)
}

func TestReadTreeFieldLengthLimit(t *testing.T) {
	long := string(bytes.Repeat([]byte("a"), MaxFieldLength))
	tooLong := long + "a"

	for name, child := range map[string]testChild{
		"path":   {name: long, digest: "d", status: InodeType_Regular},
		"digest": {name: "n", digest: long, status: InodeType_Regular},
		"target": {name: "n", status: InodeType_Symlink, target: long},
	} {
		tree, err := ReadTree(bytes.NewReader(encodeTree([]testChild{child})))
		assert.NoError(t, err, name)
		assert.Len(t, tree.Children, 1, name)
	}

	for name, child := range map[string]testChild{
		"path":   {name: tooLong, digest: "d", status: InodeType_Regular},
		"digest": {name: "n", digest: tooLong, status: InodeType_Regular},
		"target": {name: "n", status: InodeType_Symlink, target: tooLong},
	} {
		_, err := ReadTree(bytes.NewReader(encodeTree([]testChild{child})))
		assert.ErrorContains(t, err, "out of range", name)
	}
}

func TestReadTreeTruncatedPathOrTarget(t *testing.T) {
	// Skipped fields that end early are errors, not the end of the tree.
	path := encodeTree([]testChild{{name: "file.txt", digest: "d", status: InodeType_Regular}})
	_, err := ReadTree(bytes.NewReader(path[:4+8+3]))
	assert.ErrorIs(t, err, io.ErrUnexpectedEOF)

	target := encodeTree([]testChild{{name: "link", status: InodeType_Symlink, target: "file.txt"}})
	_, err = ReadTree(bytes.NewReader(target[:len(target)-3]))
	assert.ErrorIs(t, err, io.ErrUnexpectedEOF)
}
