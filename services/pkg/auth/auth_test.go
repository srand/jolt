package auth

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/base64"
	"encoding/pem"
	"fmt"
	"math/big"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/emptypb"
)

var ctx = context.Background()

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

	identity, err := a.Authorize(ctx, "", Write)
	assert.NoError(t, err)
	assert.Equal(t, "anonymous", identity.Name)

	_, err = a.Authorize(ctx, "unknown", Read)
	assert.ErrorIs(t, err, ErrUnauthenticated)
}

func TestWithTokensAnonymousHasNoPermissions(t *testing.T) {
	a := newTestAuthenticator(t, nil)

	_, err := a.Authorize(ctx, "", Read)
	assert.ErrorIs(t, err, ErrUnauthenticated)

	identity, err := a.Authorize(ctx, "ci-token", Write)
	assert.NoError(t, err)
	assert.Equal(t, "ci", identity.Name)

	_, err = a.Authorize(ctx, "reader-token", Read)
	assert.NoError(t, err)
	_, err = a.Authorize(ctx, "reader-token", Write)
	assert.ErrorIs(t, err, ErrPermissionDenied)

	_, err = a.Authorize(ctx, "wrong-token", Read)
	assert.ErrorIs(t, err, ErrUnauthenticated)
}

func TestConfiguredAnonymousPermissions(t *testing.T) {
	a := newTestAuthenticator(t, permissions(Read))

	_, err := a.Authorize(ctx, "", Read)
	assert.NoError(t, err)
	_, err = a.Authorize(ctx, "", Write)
	assert.ErrorIs(t, err, ErrUnauthenticated)
	_, err = a.Authorize(ctx, "ci-token", Write)
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

	code := func(ctx context.Context, permission Permission) codes.Code {
		_, err := a.authorizeContext(ctx, permission)
		return status.Code(err)
	}
	assert.Equal(t, codes.Unauthenticated, code(context.Background(), Read))
	assert.Equal(t, codes.PermissionDenied, code(withToken("Bearer reader-token"), Write))

	// The context of an authorized call has its client
	ctx, err := a.authorizeContext(withToken("Bearer ci-token"), Write)
	assert.NoError(t, err)
	identity, ok := IdentityFromContext(ctx)
	assert.True(t, ok)
	assert.Equal(t, "ci", identity.Name)
}

func TestDialOptions(t *testing.T) {
	target, opts, err := DialOptions("tcp://scheduler", ClientOptions{})
	assert.NoError(t, err)
	assert.Equal(t, "scheduler:9090", target)
	assert.Len(t, opts, 1)

	_, _, err = DialOptions("tcp://scheduler:9090", ClientOptions{Token: "token"})
	assert.ErrorContains(t, err, "without TLS")

	_, opts, err = DialOptions("tcp://scheduler:9090", ClientOptions{Token: "token", AllowInsecureToken: true})
	assert.NoError(t, err)
	assert.Len(t, opts, 2)

	_, opts, err = DialOptions("tls://scheduler:9090", ClientOptions{Token: "token"})
	assert.NoError(t, err)
	assert.Len(t, opts, 2)

	_, _, err = DialOptions("tls://scheduler:9090", ClientOptions{CACert: "/nonexistent.pem"})
	assert.Error(t, err)

	_, _, err = DialOptions("http://scheduler:9090", ClientOptions{})
	assert.Error(t, err)

	md, err := tokenCredentials{token: "token"}.GetRequestMetadata(context.Background())
	assert.NoError(t, err)
	assert.Equal(t, "Bearer token", md["authorization"])
	assert.Equal(t, "token", TokenFromHeader(md["authorization"]))
}

// Writes a self-signed certificate for localhost and its key to files.
func writeCertificate(t *testing.T) (string, string) {
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	assert.NoError(t, err)
	template := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "localhost"},
		DNSNames:              []string{"localhost"},
		NotBefore:             time.Now().Add(-time.Hour),
		NotAfter:              time.Now().Add(time.Hour),
		IsCA:                  true,
		BasicConstraintsValid: true,
		KeyUsage:              x509.KeyUsageDigitalSignature | x509.KeyUsageCertSign,
		ExtKeyUsage:           []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
	}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	assert.NoError(t, err)
	keyDer, err := x509.MarshalECPrivateKey(key)
	assert.NoError(t, err)

	dir := t.TempDir()
	cert := filepath.Join(dir, "cert.pem")
	keyFile := filepath.Join(dir, "key.pem")
	assert.NoError(t, os.WriteFile(cert, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}), 0600))
	assert.NoError(t, os.WriteFile(keyFile, pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: keyDer}), 0600))
	return cert, keyFile
}

func TestTLSWithToken(t *testing.T) {
	cert, key := writeCertificate(t)
	a := newTestAuthenticator(t, nil)

	creds, err := ServerCredentials(cert, key)
	assert.NoError(t, err)
	// Any method is answered, and authorized by the interceptors
	echo := grpc.UnknownServiceHandler(func(srv any, stream grpc.ServerStream) error {
		if err := stream.RecvMsg(&emptypb.Empty{}); err != nil {
			return err
		}
		return stream.SendMsg(&emptypb.Empty{})
	})
	server := grpc.NewServer(append([]grpc.ServerOption{creds, echo}, a.ServerOptions(func(string) Permission { return Write })...)...)
	listener, err := net.Listen("tcp", "localhost:0")
	assert.NoError(t, err)
	go server.Serve(listener)
	defer server.Stop()

	check := func(options ClientOptions) error {
		port := listener.Addr().(*net.TCPAddr).Port
		target, opts, err := DialOptions(fmt.Sprintf("tls://localhost:%d", port), options)
		assert.NoError(t, err)
		conn, err := grpc.NewClient(target, opts...)
		assert.NoError(t, err)
		defer conn.Close()
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		return conn.Invoke(ctx, "/test.Service/Method", &emptypb.Empty{}, &emptypb.Empty{})
	}

	// The certificate isn't trusted without the authority
	assert.Equal(t, codes.Unavailable, status.Code(check(ClientOptions{Token: "ci-token"})))
	assert.Equal(t, codes.Unauthenticated, status.Code(check(ClientOptions{CACert: cert})))
	assert.Equal(t, codes.PermissionDenied, status.Code(check(ClientOptions{CACert: cert, Token: "reader-token"})))
	assert.NoError(t, check(ClientOptions{CACert: cert, Token: "ci-token"}))
}

func TestNewToken(t *testing.T) {
	first, err := NewToken()
	assert.NoError(t, err)
	second, err := NewToken()
	assert.NoError(t, err)
	assert.NotEqual(t, first, second)
	assert.Len(t, HashToken(first), 64)
}

func TestIdentityIsAnonymousWithoutToken(t *testing.T) {
	a := newTestAuthenticator(t, permissions(Read))

	identity, err := a.Authenticate(ctx, "")
	assert.NoError(t, err)
	assert.True(t, identity.Anonymous)

	identity, err = a.Authenticate(ctx, "ci-token")
	assert.NoError(t, err)
	assert.False(t, identity.Anonymous)
}

func TestSingleTokenAnonymousHasNoPermissions(t *testing.T) {
	a, err := New(Config{Tokens: []Token{{Name: "ci", Hash: HashToken("ci-token"), Permissions: []Permission{Read}}}}, Read, Write)
	assert.NoError(t, err)

	_, err = a.Authorize(ctx, "", Read)
	assert.ErrorIs(t, err, ErrUnauthenticated)
}

func TestTokenHashMustBeSHA256(t *testing.T) {
	for _, hash := range []string{
		HashToken("x")[:62],
		HashToken("x") + "00",
		"zz" + HashToken("x")[2:],
	} {
		_, err := New(Config{Tokens: []Token{{Name: "bad", Hash: hash}}}, Read)
		assert.ErrorContains(t, err, "invalid SHA-256 hash", hash)
	}
}

func TestTokenShapedLikeJWTWithoutOIDC(t *testing.T) {
	// Tokens are only verified by an OIDC provider if one is configured.
	a := newTestAuthenticator(t, nil)
	_, err := a.Authorize(ctx, "a.b.c", Read)
	assert.ErrorIs(t, err, ErrUnauthenticated)
}

func TestNewTokenHas256Bits(t *testing.T) {
	token, err := NewToken()
	assert.NoError(t, err)
	data, err := base64.RawURLEncoding.DecodeString(token)
	assert.NoError(t, err)
	assert.Len(t, data, 32)
}

func TestUnaryCallsAreAuthorized(t *testing.T) {
	a := newTestAuthenticator(t, nil)

	// A service with a unary method, which answers with the name of its client
	type unaryService any
	service := &grpc.ServiceDesc{
		ServiceName: "test.Unary",
		HandlerType: (*unaryService)(nil),
		Methods: []grpc.MethodDesc{{
			MethodName: "Method",
			Handler: func(srv any, ctx context.Context, dec func(any) error, interceptor grpc.UnaryServerInterceptor) (any, error) {
				in := &emptypb.Empty{}
				if err := dec(in); err != nil {
					return nil, err
				}
				handler := func(ctx context.Context, req any) (any, error) {
					identity, ok := IdentityFromContext(ctx)
					if !ok {
						return nil, status.Error(codes.Internal, "no identity")
					}
					grpc.SetHeader(ctx, metadata.Pairs("identity", identity.Name))
					return &emptypb.Empty{}, nil
				}
				return interceptor(ctx, in, &grpc.UnaryServerInfo{Server: srv, FullMethod: "/test.Unary/Method"}, handler)
			},
		}},
	}
	server := grpc.NewServer(a.ServerOptions(func(string) Permission { return Write })...)
	server.RegisterService(service, struct{}{})
	listener, err := net.Listen("tcp", "localhost:0")
	assert.NoError(t, err)
	go server.Serve(listener)
	defer server.Stop()

	call := func(token string) (string, error) {
		target, opts, err := DialOptions("tcp://"+listener.Addr().String(), ClientOptions{Token: token, AllowInsecureToken: true})
		assert.NoError(t, err)
		conn, err := grpc.NewClient(target, opts...)
		assert.NoError(t, err)
		defer conn.Close()
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		var header metadata.MD
		err = conn.Invoke(ctx, "/test.Unary/Method", &emptypb.Empty{}, &emptypb.Empty{}, grpc.Header(&header))
		return strings.Join(header.Get("identity"), ","), err
	}

	_, err = call("")
	assert.Equal(t, codes.Unauthenticated, status.Code(err))
	_, err = call("reader-token")
	assert.Equal(t, codes.PermissionDenied, status.Code(err))
	name, err := call("ci-token")
	assert.NoError(t, err)
	assert.Equal(t, "ci", name)
}

func TestConfigString(t *testing.T) {
	config := Config{Tokens: []Token{{Name: "ci", Hash: HashToken("ci-token"), Permissions: []Permission{Read}}}}
	assert.Equal(t, "anonymous=default tokens=[ci[read]]", config.String())

	config.Anonymous = permissions(Read)
	config.OIDC = &OIDCConfig{Issuer: "https://idp", Audience: "jolt", Groups: []Group{{Name: "dev", Permissions: []Permission{Write}}}}
	assert.Equal(t, "anonymous=[read] tokens=[ci[read]] oidc={issuer=https://idp audience=jolt permissions=[] groups=[dev[write]]}", config.String())
	assert.NotContains(t, config.String(), HashToken("ci-token"))
}
