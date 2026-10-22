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
