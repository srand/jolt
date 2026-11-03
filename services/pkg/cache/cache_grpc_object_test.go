package cache

import (
	"bytes"
	"context"
	"io"
	"net"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
)

// Serves the cache over gRPC and returns a client of the service.
func newTestClient(t *testing.T, c Cache) CacheServiceClient {
	server := grpc.NewServer()
	RegisterCacheServiceServer(server, NewCacheService(c, 64<<20))
	listener, err := net.Listen("tcp", "localhost:0")
	require.NoError(t, err)
	go server.Serve(listener)
	t.Cleanup(server.Stop)

	conn, err := grpc.NewClient(listener.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()))
	require.NoError(t, err)
	t.Cleanup(func() { conn.Close() })
	return NewCacheServiceClient(conn)
}

func testContext(t *testing.T) context.Context {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	t.Cleanup(cancel)
	return ctx
}

// Uploads an object in chunks of the given size.
func writeObject(t *testing.T, client CacheServiceClient, digest string, data []byte, chunk int) error {
	stream, err := client.WriteObject(testContext(t))
	require.NoError(t, err)
	for first := true; first || len(data) > 0; first = false {
		n := min(chunk, len(data))
		if err := stream.Send(&WriteObjectRequest{Digest: digest, Data: data[:n]}); err != nil {
			break
		}
		data = data[n:]
	}
	_, err = stream.CloseAndRecv()
	return err
}

func readObject(t *testing.T, client CacheServiceClient, digest string) ([]byte, error) {
	stream, err := client.ReadObject(testContext(t), &ReadObjectRequest{Digest: digest})
	require.NoError(t, err)
	var data []byte
	for {
		response, err := stream.Recv()
		if err == io.EOF {
			return data, nil
		}
		if err != nil {
			return nil, err
		}
		data = append(data, response.Data...)
	}
}

func TestGrpcWriteAndReadObject(t *testing.T) {
	c := newTestCache(t)
	client := newTestClient(t, c)

	// Larger than a message of the service
	data := bytes.Repeat([]byte("0123456789abcdef"), 0x2000)
	digest := blake3Digest(data)

	assert.NoError(t, writeObject(t, client, digest, data, 0x1000))
	read, err := readObject(t, client, digest)
	assert.NoError(t, err)
	assert.Equal(t, data, read)
	assert.Equal(t, int64(0), c.open.Load(), "readers left open")

	// Objects are only written once
	assert.Equal(t, codes.AlreadyExists, status.Code(writeObject(t, client, digest, data, len(data))))
}

func TestGrpcReadEmptyObject(t *testing.T) {
	c := newTestCache(t)
	client := newTestClient(t, c)
	digest := put(t, c, nil)

	read, err := readObject(t, client, digest)
	assert.NoError(t, err)
	assert.Empty(t, read)
}

func TestGrpcWriteObjectWithOtherContent(t *testing.T) {
	c := newTestCache(t)
	client := newTestClient(t, c)
	data := []byte("content")
	digest := blake3Digest(data)

	assert.Error(t, writeObject(t, client, digest, []byte("other content"), 4))
	_, err := readObject(t, client, digest)
	assert.Error(t, err)

	// The upload can be retried with the right content
	assert.NoError(t, writeObject(t, client, digest, data, 4))
	read, err := readObject(t, client, digest)
	assert.NoError(t, err)
	assert.Equal(t, data, read)
}

func TestGrpcObjectErrors(t *testing.T) {
	client := newTestClient(t, newTestCache(t))
	missing := blake3Digest([]byte("missing"))

	_, err := readObject(t, client, missing)
	assert.Equal(t, codes.Internal, status.Code(err))
	_, err = readObject(t, client, "blake3:xyz")
	assert.Equal(t, codes.InvalidArgument, status.Code(err))
	assert.Equal(t, codes.InvalidArgument, status.Code(writeObject(t, client, "blake3:xyz", []byte("data"), 4)))
}

func TestGrpcHasObject(t *testing.T) {
	c := newTestCache(t)
	client := newTestClient(t, c)
	present := put(t, c, []byte("present"))
	missing := blake3Digest([]byte("missing"))

	response, err := client.HasObject(testContext(t), &HasObjectRequest{Digest: []string{missing, present, present, missing}})
	assert.NoError(t, err)
	assert.Equal(t, []bool{false, true, true, false}, response.Present)

	response, err = client.HasObject(testContext(t), &HasObjectRequest{})
	assert.NoError(t, err)
	assert.Empty(t, response.Present)

	_, err = client.HasObject(testContext(t), &HasObjectRequest{Digest: []string{present, "blake3:xyz"}})
	assert.Equal(t, codes.InvalidArgument, status.Code(err))
}

func TestShardOf(t *testing.T) {
	// Digests are spread over all shards by their first byte.
	for hex, want := range map[string]uint8{
		"00ab": 0x00,
		"09ab": 0x09,
		"0aab": 0x0a,
		"a0ab": 0xa0,
		"f9ab": 0xf9,
		"ffab": 0xff,
		"7c":   0x7c,
		"7":    0,
		"":     0,
	} {
		assert.Equal(t, want, shardOf(hex), hex)
	}
}
