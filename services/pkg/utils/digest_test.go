package utils

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestParseDigestOk(t *testing.T) {
	d, err := ParseDigest("7d97e98f8af710c7e7fe703abc8f639e0ee507c4")
	assert.NoError(t, err)
	assert.Equal(t, d.Algorithm(), Sha1Algorithm)
	assert.Equal(t, d.Hex(), "7d97e98f8af710c7e7fe703abc8f639e0ee507c4")

	d, err = ParseDigest("sha1:7d97e98f8af710c7e7fe703abc8f639e0ee507c4")
	assert.NoError(t, err)
	assert.Equal(t, d.Algorithm(), Sha1Algorithm)
	assert.Equal(t, d.Hex(), "7d97e98f8af710c7e7fe703abc8f639e0ee507c4")

	d, err = ParseDigest("sha256:2851d3a78dea9edc6ada3a8c41b47c4cfe861eb41908a490b9dc59011dcbc8a0")
	assert.NoError(t, err)
	assert.Equal(t, d.Algorithm(), Sha256Algorithm)
	assert.Equal(t, d.Hex(), "2851d3a78dea9edc6ada3a8c41b47c4cfe861eb41908a490b9dc59011dcbc8a0")

	// Upper case hex refers to the same object as lower case hex
	d, err = ParseDigest("sha1:7D97E98F8AF710C7E7FE703ABC8F639E0EE507C4")
	assert.NoError(t, err)
	assert.Equal(t, d.Hex(), "7d97e98f8af710c7e7fe703abc8f639e0ee507c4")
}

func TestParseDigestFail(t *testing.T) {
	// Invalid length of hex
	_, err := ParseDigest("7d97e98f8af710c7e7fe703abc8f639e0ee7c4")
	assert.Error(t, err)

	// Invalid length of hex
	_, err = ParseDigest("sha1:7d97e98f8af710c7e7fe703abc8f639e0ee507")
	assert.Error(t, err)

	// Invalid length of hex
	_, err = ParseDigest("sha256:2851d3a78dea9edc6ada3a8c41b474cfe861eb41908a490b9dc59011dcbc8a0")
	assert.Error(t, err)

	// Not hex
	_, err = ParseDigest("sha1:../../../../../../../../../../etc/passwd")
	assert.Error(t, err)

	// Empty
	_, err = ParseDigest("sha1:")
	assert.Error(t, err)
}

func TestDigestString(t *testing.T) {
	// The string form includes the algorithm and parses back to the same digest.
	for _, s := range []string{
		"sha1:7d97e98f8af710c7e7fe703abc8f639e0ee507c4",
		"blake3:fe3d8d834ae52bf4961af02f1b2db179331137c3281d1dd8a2dd565949eacabe",
	} {
		d, err := ParseDigest(s)
		assert.NoError(t, err)
		assert.Equal(t, s, d.String())
	}
}

func TestParseDigestCanonicalHex(t *testing.T) {
	// Mixed case refers to the same object and is stored in lower case.
	d, err := ParseDigest("blake3:FE3d8D834ae52bf4961af02f1b2db179331137c3281d1dd8a2dd565949eacABE")
	assert.NoError(t, err)
	assert.Equal(t, "fe3d8d834ae52bf4961af02f1b2db179331137c3281d1dd8a2dd565949eacabe", d.Hex())

	// Any character that is not a hex digit is rejected, wherever it is.
	for _, s := range []string{
		"sha1:g7d97e98f8af710c7e7fe703abc8f639e0ee507c",
		"sha1:7d97e98f8af710c7e7fe703abc8f639e0ee507cg",
		"sha1:7d97e98f8af710c7e7fe/03abc8f639e0ee507c4",
		"sha1:7d97e98f8af710c7e7fe.03abc8f639e0ee507c4",
		"sha1:7d97e98f8af710c7e7fe 03abc8f639e0ee507c4",
		"sha1:7d97e98f8af710c7e7fe\x0003abc8f639e0ee507c4",
		// Odd number of hex digits
		"sha1:7d97e98f8af710c7e7fe703abc8f639e0ee507c",
	} {
		_, err := ParseDigest(s)
		assert.Error(t, err, "%q", s)
	}
}

func BenchmarkParseDigest(b *testing.B) {
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		if _, err := ParseDigest("blake3:fe3d8d834ae52bf4961af02f1b2db179331137c3281d1dd8a2dd565949eacabe"); err != nil {
			b.Fatal(err)
		}
	}
}
