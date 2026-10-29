// Package auth authenticates the clients of services with bearer tokens and
// authorizes their requests by the permissions granted to the tokens.
package auth

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"net/http"
	"os"
	"slices"
	"strings"

	"github.com/srand/jolt/scheduler/pkg/utils"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

// A permission granted to clients, such as reading or writing the cache.
type Permission string

const (
	Read  Permission = "read"
	Write Permission = "write"
)

var (
	ErrUnauthenticated  = errors.New("unauthenticated")
	ErrPermissionDenied = errors.New("permission denied")
)

// A token and the permissions it grants.
type Token struct {
	// Name of the client, used in logs.
	Name string `mapstructure:"name"`
	// Hex encoded SHA-256 hash of the token, so that the configuration
	// doesn't contain the token itself. See HashToken.
	Hash string `mapstructure:"sha256"`
	// Permissions granted to the client.
	Permissions []Permission `mapstructure:"permissions"`
}

type Config struct {
	// Permissions of clients without a token. Without tokens, clients have
	// all permissions unless configured otherwise. With tokens, they have
	// none unless configured otherwise.
	Anonymous *[]Permission `mapstructure:"anonymous"`
	// Tokens accepted from clients.
	Tokens []Token `mapstructure:"tokens"`
	// Tokens issued by an OpenID Connect provider, accepted in addition to
	// the tokens above.
	OIDC *OIDCConfig `mapstructure:"oidc"`
}

// An authenticated client.
type Identity struct {
	Name        string
	Permissions []Permission
	// The client didn't present a token.
	Anonymous bool
}

// Allows returns true if the client has the permission.
func (i *Identity) Allows(permission Permission) bool {
	return slices.Contains(i.Permissions, permission)
}

type Authenticator struct {
	anonymous Identity
	tokens    map[[sha256.Size]byte]Identity
	oidc      *oidcVerifier
}

// New creates an authenticator from the configuration. Permissions are
// those of the service, which grants all of them when it isn't configured.
func New(config Config, permissions ...Permission) (*Authenticator, error) {
	a := &Authenticator{
		anonymous: Identity{Name: "anonymous", Permissions: permissions, Anonymous: true},
		tokens:    map[[sha256.Size]byte]Identity{},
	}

	if config.Anonymous != nil {
		a.anonymous.Permissions = *config.Anonymous
	} else if len(config.Tokens) > 0 || config.OIDC != nil {
		a.anonymous.Permissions = nil
	}

	if config.OIDC != nil {
		verifier, err := newOIDCVerifier(*config.OIDC)
		if err != nil {
			return nil, err
		}
		a.oidc = verifier
	}

	for _, token := range config.Tokens {
		hash, err := hex.DecodeString(token.Hash)
		if err != nil || len(hash) != sha256.Size {
			return nil, fmt.Errorf("invalid SHA-256 hash of token %q", token.Name)
		}
		a.tokens[[sha256.Size]byte(hash)] = Identity{Name: token.Name, Permissions: token.Permissions}
	}

	for _, identity := range append([]Identity{a.anonymous}, a.identities()...) {
		for _, permission := range identity.Permissions {
			if !slices.Contains(permissions, permission) {
				return nil, fmt.Errorf("invalid permission %q of %s, valid permissions are %v", permission, identity.Name, permissions)
			}
		}
	}

	return a, nil
}

func (a *Authenticator) identities() []Identity {
	identities := []Identity{}
	for _, identity := range a.tokens {
		identities = append(identities, identity)
	}
	if a.oidc != nil {
		identities = append(identities, a.oidc.identities()...)
	}
	return identities
}

// Authenticate returns the client with the token. Clients without a token
// are anonymous. Tokens that aren't configured are verified as tokens of the
// OpenID Connect provider, if there is one.
func (a *Authenticator) Authenticate(ctx context.Context, token string) (*Identity, error) {
	if token == "" {
		return &a.anonymous, nil
	}
	if identity, ok := a.tokens[sha256.Sum256([]byte(token))]; ok {
		return &identity, nil
	}
	if a.oidc != nil && strings.Count(token, ".") == 2 {
		return a.oidc.Verify(ctx, token)
	}
	return nil, ErrUnauthenticated
}

// Authorize returns the client with the token if it has the permission.
func (a *Authenticator) Authorize(ctx context.Context, token string, permission Permission) (*Identity, error) {
	identity, err := a.Authenticate(ctx, token)
	if err != nil {
		return nil, err
	}
	if !identity.Allows(permission) {
		// Anonymous clients may have permission with a token
		if token == "" {
			return nil, ErrUnauthenticated
		}
		return nil, ErrPermissionDenied
	}
	return identity, nil
}

// TokenFromHeader returns the token in the value of an Authorization header.
// Both bearer tokens and the password of basic authentication are accepted.
func TokenFromHeader(header string) string {
	scheme, credentials, found := strings.Cut(header, " ")
	if !found {
		return ""
	}
	switch strings.ToLower(scheme) {
	case "bearer":
		return strings.TrimSpace(credentials)
	case "basic":
		decoded, err := base64.StdEncoding.DecodeString(strings.TrimSpace(credentials))
		if err != nil {
			return ""
		}
		_, password, _ := strings.Cut(string(decoded), ":")
		return password
	}
	return ""
}

// HttpHandler authorizes requests with the permission that the function
// returns for them before passing them on to the handler.
func (a *Authenticator) HttpHandler(handler http.Handler, permission func(*http.Request) Permission) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, err := a.Authorize(r.Context(), TokenFromHeader(r.Header.Get("Authorization")), permission(r))
		switch {
		case errors.Is(err, ErrUnauthenticated):
			// Browsers ask for the password of basic authentication,
			// which can be the token
			w.Header().Add("WWW-Authenticate", `Bearer realm="jolt"`)
			w.Header().Add("WWW-Authenticate", `Basic realm="jolt"`)
			http.Error(w, err.Error(), http.StatusUnauthorized)
		case err != nil:
			http.Error(w, err.Error(), http.StatusForbidden)
		default:
			handler.ServeHTTP(w, r)
		}
	})
}

type identityKey struct{}

// IdentityFromContext returns the client that made a call, which the
// interceptors of ServerOptions add to the context of the call.
func IdentityFromContext(ctx context.Context) (*Identity, bool) {
	identity, ok := ctx.Value(identityKey{}).(*Identity)
	return identity, ok
}

// ContextWithIdentity returns a context with the client that made a call.
func ContextWithIdentity(ctx context.Context, identity *Identity) context.Context {
	return context.WithValue(ctx, identityKey{}, identity)
}

// authorizeContext returns the context of a call with its client, if the
// client has the permission.
func (a *Authenticator) authorizeContext(ctx context.Context, permission Permission) (context.Context, error) {
	token := ""
	if md, ok := metadata.FromIncomingContext(ctx); ok {
		if values := md.Get("authorization"); len(values) > 0 {
			token = TokenFromHeader(values[0])
		}
	}
	identity, err := a.Authorize(ctx, token, permission)
	switch {
	case errors.Is(err, ErrUnauthenticated):
		return nil, status.Error(codes.Unauthenticated, err.Error())
	case err != nil:
		return nil, status.Error(codes.PermissionDenied, err.Error())
	}
	return ContextWithIdentity(ctx, identity), nil
}

// A server stream whose context includes the client.
type identityStream struct {
	grpc.ServerStream
	ctx context.Context
}

func (s identityStream) Context() context.Context {
	return s.ctx
}

// ServerOptions returns gRPC server options that authorize calls with the
// permission that the function returns for their methods.
func (a *Authenticator) ServerOptions(permission func(method string) Permission) []grpc.ServerOption {
	return []grpc.ServerOption{
		grpc.ChainUnaryInterceptor(func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
			ctx, err := a.authorizeContext(ctx, permission(info.FullMethod))
			if err != nil {
				return nil, err
			}
			return handler(ctx, req)
		}),
		grpc.ChainStreamInterceptor(func(srv any, ss grpc.ServerStream, info *grpc.StreamServerInfo, handler grpc.StreamHandler) error {
			ctx, err := a.authorizeContext(ss.Context(), permission(info.FullMethod))
			if err != nil {
				return err
			}
			return handler(srv, identityStream{ServerStream: ss, ctx: ctx})
		}),
	}
}

type tokenCredentials struct {
	token  string
	secure bool
}

func (t tokenCredentials) GetRequestMetadata(ctx context.Context, uri ...string) (map[string]string, error) {
	return map[string]string{"authorization": "Bearer " + t.token}, nil
}

func (t tokenCredentials) RequireTransportSecurity() bool {
	return t.secure
}

// Options of clients that connect to a service.
type ClientOptions struct {
	// PEM file with the certificates of the authorities that the
	// certificates of services are verified with, in addition to those of
	// the system.
	CACert string
	// Token that authenticates the client.
	Token string
	// Send the token over connections without TLS.
	AllowInsecureToken bool
}

// DialOptions returns the target and gRPC dial options for a connection to
// a service with a tcp:// or tls:// URI. The token is sent with each call,
// but only over TLS unless that is explicitly allowed.
func DialOptions(uri string, options ClientOptions) (string, []grpc.DialOption, error) {
	target, err := utils.ParseGrpcUrl(uri)
	if err != nil {
		return "", nil, err
	}

	secure := strings.HasPrefix(uri, "tls://")
	opts := []grpc.DialOption{}

	if secure {
		config, err := TLSConfig(options.CACert)
		if err != nil {
			return "", nil, err
		}
		opts = append(opts, grpc.WithTransportCredentials(credentials.NewTLS(config)))
	} else {
		opts = append(opts, grpc.WithTransportCredentials(insecure.NewCredentials()))
	}

	if options.Token != "" {
		if !secure && !options.AllowInsecureToken {
			return "", nil, fmt.Errorf("refusing to send a token to %s without TLS, use a tls:// URI", uri)
		}
		opts = append(opts, grpc.WithPerRPCCredentials(tokenCredentials{token: options.Token, secure: secure}))
	}

	return target, opts, nil
}

// TLSConfig returns the TLS configuration of clients, which verify the
// certificates of services with the authorities of the system and those in
// the PEM file, if any.
func TLSConfig(caCert string) (*tls.Config, error) {
	pool, err := x509.SystemCertPool()
	if err != nil {
		pool = x509.NewCertPool()
	}
	if caCert != "" {
		data, err := os.ReadFile(caCert)
		if err != nil {
			return nil, err
		}
		if !pool.AppendCertsFromPEM(data) {
			return nil, fmt.Errorf("no certificates in %s", caCert)
		}
	}
	return &tls.Config{RootCAs: pool, MinVersion: tls.VersionTLS12}, nil
}

// ServerCredentials returns the gRPC server option that serves TLS with
// the certificate and private key.
func ServerCredentials(cert, key string) (grpc.ServerOption, error) {
	creds, err := credentials.NewServerTLSFromFile(cert, key)
	if err != nil {
		return nil, err
	}
	return grpc.Creds(creds), nil
}

// NewToken returns a random token.
func NewToken() (string, error) {
	data := make([]byte, 32)
	if _, err := rand.Read(data); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(data), nil
}

// HashToken returns the hash of a token, as written in the configuration.
func HashToken(token string) string {
	hash := sha256.Sum256([]byte(token))
	return hex.EncodeToString(hash[:])
}

// String returns a description of the configuration without the hashes of tokens.
func (c *Config) String() string {
	anonymous := "default"
	if c.Anonymous != nil {
		anonymous = fmt.Sprint(*c.Anonymous)
	}
	names := []string{}
	for _, token := range c.Tokens {
		names = append(names, fmt.Sprintf("%s%v", token.Name, token.Permissions))
	}
	if c.OIDC != nil {
		return fmt.Sprintf("anonymous=%s tokens=%v oidc={%s}", anonymous, names, c.OIDC)
	}
	return fmt.Sprintf("anonymous=%s tokens=%v", anonymous, names)
}
