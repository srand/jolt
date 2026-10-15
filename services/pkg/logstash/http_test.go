package logstash

import (
	"bufio"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/labstack/echo/v4"
	"github.com/spf13/afero"
	"github.com/stretchr/testify/assert"
)

func newTestHttpServer(t *testing.T) (*httptest.Server, LogStash) {
	t.Helper()

	config := new(MockLogStashConfig)
	config.On("MaxSize").Return(0x100000)
	stash := NewLogStash(config, afero.NewMemMapFs())

	e := echo.New()
	NewHttpHandler(stash, e)
	server := httptest.NewServer(e)
	t.Cleanup(server.Close)

	return server, stash
}

// Reads one line in the background, so the test can tell "not yet written"
// from "written but stuck in a buffer".
func readLineAsync(reader *bufio.Reader) chan string {
	out := make(chan string, 1)
	go func() {
		line, err := reader.ReadString('\n')
		if err != nil {
			out <- ""
			return
		}
		out <- line
	}()
	return out
}

// The default path: no follow, so the response ends at the end of the log even
// though a writer is still open.
func TestGetLogWithoutFollowEndsAtEndOfLog(t *testing.T) {
	server, stash := newTestHttpServer(t)

	writer, err := stash.Append("log1")
	assert.NoError(t, err)
	assert.NoError(t, writer.WriteLine(testLine("first")))
	defer writer.Close()

	response, err := http.Get(server.URL + "/logs/log1")
	assert.NoError(t, err)
	defer response.Body.Close()
	assert.Equal(t, http.StatusOK, response.StatusCode)

	reader := bufio.NewReader(response.Body)

	select {
	case line := <-readLineAsync(reader):
		assert.Contains(t, line, "first")
	case <-time.After(2 * time.Second):
		t.Fatal("the log line never arrived")
	}

	// The body must end even though a writer is still open.
	select {
	case line := <-readLineAsync(reader):
		assert.Equal(t, "", line)
	case <-time.After(2 * time.Second):
		t.Fatal("a plain read did not end at the end of the log")
	}
}

func TestGetLogWithFollowStreamsLinesAsTheyAreWritten(t *testing.T) {
	server, stash := newTestHttpServer(t)

	writer, err := stash.Append("log1")
	assert.NoError(t, err)
	assert.NoError(t, writer.WriteLine(testLine("first")))

	response, err := http.Get(server.URL + "/logs/log1?follow=1")
	assert.NoError(t, err)
	defer response.Body.Close()
	assert.Equal(t, http.StatusOK, response.StatusCode)

	reader := bufio.NewReader(response.Body)

	select {
	case line := <-readLineAsync(reader):
		assert.Contains(t, line, "first")
	case <-time.After(2 * time.Second):
		t.Fatal("the first line never arrived; is the response being buffered?")
	}

	assert.NoError(t, writer.WriteLine(testLine("second")))

	select {
	case line := <-readLineAsync(reader):
		assert.Contains(t, line, "second")
	case <-time.After(2 * time.Second):
		t.Fatal("a line written after the request started never arrived")
	}

	assert.NoError(t, writer.Close())

	select {
	case line := <-readLineAsync(reader):
		assert.Equal(t, "", line)
	case <-time.After(2 * time.Second):
		t.Fatal("the response did not end once the log was complete")
	}
}

// Review Focus 3: following a log nothing is writing any more must end, not hang.
func TestGetLogWithFollowEndsOnACompletedLog(t *testing.T) {
	server, stash := newTestHttpServer(t)

	writer, err := stash.Append("log1")
	assert.NoError(t, err)
	assert.NoError(t, writer.WriteLine(testLine("first")))
	assert.NoError(t, writer.Close())

	response, err := http.Get(server.URL + "/logs/log1?follow=1")
	assert.NoError(t, err)
	defer response.Body.Close()

	reader := bufio.NewReader(response.Body)

	select {
	case line := <-readLineAsync(reader):
		assert.Contains(t, line, "first")
	case <-time.After(2 * time.Second):
		t.Fatal("the log line never arrived")
	}

	select {
	case line := <-readLineAsync(reader):
		assert.Equal(t, "", line)
	case <-time.After(2 * time.Second):
		t.Fatal("following a completed log did not end")
	}
}

func TestGetLogPreservesTheLineFormat(t *testing.T) {
	server, stash := newTestHttpServer(t)

	writer, err := stash.Append("log1")
	assert.NoError(t, err)
	assert.NoError(t, writer.WriteLine(testLine("hello")))
	assert.NoError(t, writer.Close())

	response, err := http.Get(server.URL + "/logs/log1")
	assert.NoError(t, err)
	defer response.Body.Close()

	line, err := bufio.NewReader(response.Body).ReadString('\n')
	assert.NoError(t, err)

	// The dashboard filters on these exact columns.
	assert.Equal(t, byte('['), line[27], "column 27 must be the level bracket")
	assert.Equal(t, "INFO", strings.TrimSpace(line[28:35]), "columns 28-35 must be the level")
}
