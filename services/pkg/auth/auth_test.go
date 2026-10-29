package auth

import (
	"context"
	"encoding/base64"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

func permissions(p ...Permission) *[]Permission {
	return &p
}

func newTestAuthenticator(t *testing.T, anonymous *[]Permission) *Authenticator {
	a, err := New(Config{
		Anonymous: anonymous,
		Tokens: []Token{
			{Name: "ci", Hash: HashToken("ci-token"), Permissions: []Permission{Read, Write}},
			{Name: "reader", Hash: HashToken("reader-token"), Permissions: []Permission{Read}},
		},
	}, Read, Write)
	assert.NoError(t, err)
	return a
}

func TestWithoutTokensAnonymousHasAllPermissions(t *testing.T) {
	a, err := New(Config{}, Read, Write)
	assert.NoError(t, err)

	identity, err := a.Authorize("", Write)
	assert.NoError(t, err)
	assert.Equal(t, "anonymous", identity.Name)

	_, err = a.Authorize("unknown", Read)
	assert.ErrorIs(t, err, ErrUnauthenticated)
}

func TestWithTokensAnonymousHasNoPermissions(t *testing.T) {
	a := newTestAuthenticator(t, nil)

	_, err := a.Authorize("", Read)
	assert.ErrorIs(t, err, ErrUnauthenticated)

	identity, err := a.Authorize("ci-token", Write)
	assert.NoError(t, err)
	assert.Equal(t, "ci", identity.Name)

	_, err = a.Authorize("reader-token", Read)
	assert.NoError(t, err)
	_, err = a.Authorize("reader-token", Write)
	assert.ErrorIs(t, err, ErrPermissionDenied)

	_, err = a.Authorize("wrong-token", Read)
	assert.ErrorIs(t, err, ErrUnauthenticated)
}

func TestConfiguredAnonymousPermissions(t *testing.T) {
	a := newTestAuthenticator(t, permissions(Read))

	_, err := a.Authorize("", Read)
	assert.NoError(t, err)
	_, err = a.Authorize("", Write)
	assert.ErrorIs(t, err, ErrUnauthenticated)
	_, err = a.Authorize("ci-token", Write)
	assert.NoError(t, err)
}

func TestInvalidConfiguration(t *testing.T) {
	_, err := New(Config{Tokens: []Token{{Name: "bad", Hash: "1234"}}}, Read, Write)
	assert.Error(t, err)

	_, err = New(Config{Tokens: []Token{{Name: "bad", Hash: HashToken("x"), Permissions: []Permission{"admin"}}}}, Read, Write)
	assert.Error(t, err)

	_, err = New(Config{Anonymous: permissions("admin")}, Read, Write)
	assert.Error(t, err)
}

func TestTokenFromHeader(t *testing.T) {
	basic := base64.StdEncoding.EncodeToString([]byte("user:secret"))
	assert.Equal(t, "secret", TokenFromHeader("Bearer secret"))
	assert.Equal(t, "secret", TokenFromHeader("bearer secret"))
	assert.Equal(t, "secret", TokenFromHeader("Basic "+basic))
	assert.Equal(t, "", TokenFromHeader("Basic not-base64!"))
	assert.Equal(t, "", TokenFromHeader("Digest secret"))
	assert.Equal(t, "", TokenFromHeader(""))
}

func TestHttpHandler(t *testing.T) {
	a := newTestAuthenticator(t, permissions(Read))
	ok := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	handler := a.HttpHandler(ok, func(r *http.Request) Permission {
		if r.Method == http.MethodPut {
			return Write
		}
		return Read
	})

	request := func(method, header string) *httptest.ResponseRecorder {
		r := httptest.NewRequest(method, "/files/a", nil)
		if header != "" {
			r.Header.Set("Authorization", header)
		}
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		return w
	}

	assert.Equal(t, http.StatusOK, request(http.MethodGet, "").Code)
	response := request(http.MethodPut, "")
	assert.Equal(t, http.StatusUnauthorized, response.Code)
	assert.Equal(t, []string{`Bearer realm="jolt"`, `Basic realm="jolt"`}, response.Header().Values("WWW-Authenticate"))
	assert.Equal(t, http.StatusUnauthorized, request(http.MethodPut, "Bearer wrong-token").Code)
	assert.Equal(t, http.StatusForbidden, request(http.MethodPut, "Bearer reader-token").Code)
	assert.Equal(t, http.StatusOK, request(http.MethodPut, "Bearer ci-token").Code)
}

func TestAuthorizeContext(t *testing.T) {
	a := newTestAuthenticator(t, nil)
	withToken := func(header string) context.Context {
		return metadata.NewIncomingContext(context.Background(), metadata.Pairs("authorization", header))
	}

	assert.Equal(t, codes.Unauthenticated, status.Code(a.authorizeContext(context.Background(), Read)))
	assert.Equal(t, codes.PermissionDenied, status.Code(a.authorizeContext(withToken("Bearer reader-token"), Write)))
	assert.NoError(t, a.authorizeContext(withToken("Bearer ci-token"), Write))
}

func TestDialOptions(t *testing.T) {
	assert.Empty(t, DialOptions(""))
	assert.Len(t, DialOptions("token"), 1)

	md, err := tokenCredentials("token").GetRequestMetadata(context.Background())
	assert.NoError(t, err)
	assert.Equal(t, "Bearer token", md["authorization"])
	assert.Equal(t, "token", TokenFromHeader(md["authorization"]))
}

func TestNewToken(t *testing.T) {
	first, err := NewToken()
	assert.NoError(t, err)
	second, err := NewToken()
	assert.NoError(t, err)
	assert.NotEqual(t, first, second)
	assert.Len(t, HashToken(first), 64)
}
