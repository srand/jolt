// Package auth authenticates the clients of services with bearer tokens and
// authorizes their requests by the permissions granted to the tokens.
package auth

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"net/http"
	"slices"
	"strings"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
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
}

// An authenticated client.
type Identity struct {
	Name        string
	Permissions []Permission
}

// Allows returns true if the client has the permission.
func (i *Identity) Allows(permission Permission) bool {
	return slices.Contains(i.Permissions, permission)
}

type Authenticator struct {
	anonymous Identity
	tokens    map[[sha256.Size]byte]Identity
}

// New creates an authenticator from the configuration. Permissions are
// those of the service, which grants all of them when it isn't configured.
func New(config Config, permissions ...Permission) (*Authenticator, error) {
	a := &Authenticator{
		anonymous: Identity{Name: "anonymous", Permissions: permissions},
		tokens:    map[[sha256.Size]byte]Identity{},
	}

	if config.Anonymous != nil {
		a.anonymous.Permissions = *config.Anonymous
	} else if len(config.Tokens) > 0 {
		a.anonymous.Permissions = nil
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
	return identities
}

// Authenticate returns the client with the token. Clients without a token
// are anonymous.
func (a *Authenticator) Authenticate(token string) (*Identity, error) {
	if token == "" {
		return &a.anonymous, nil
	}
	identity, ok := a.tokens[sha256.Sum256([]byte(token))]
	if !ok {
		return nil, ErrUnauthenticated
	}
	return &identity, nil
}

// Authorize returns the client with the token if it has the permission.
func (a *Authenticator) Authorize(token string, permission Permission) (*Identity, error) {
	identity, err := a.Authenticate(token)
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
		_, err := a.Authorize(TokenFromHeader(r.Header.Get("Authorization")), permission(r))
		switch {
		case errors.Is(err, ErrUnauthenticated):
			w.Header().Set("WWW-Authenticate", `Bearer realm="jolt"`)
			http.Error(w, err.Error(), http.StatusUnauthorized)
		case err != nil:
			http.Error(w, err.Error(), http.StatusForbidden)
		default:
			handler.ServeHTTP(w, r)
		}
	})
}

func (a *Authenticator) authorizeContext(ctx context.Context, permission Permission) error {
	token := ""
	if md, ok := metadata.FromIncomingContext(ctx); ok {
		if values := md.Get("authorization"); len(values) > 0 {
			token = TokenFromHeader(values[0])
		}
	}
	_, err := a.Authorize(token, permission)
	switch {
	case errors.Is(err, ErrUnauthenticated):
		return status.Error(codes.Unauthenticated, err.Error())
	case err != nil:
		return status.Error(codes.PermissionDenied, err.Error())
	}
	return nil
}

// ServerOptions returns gRPC server options that authorize calls with the
// permission that the function returns for their methods.
func (a *Authenticator) ServerOptions(permission func(method string) Permission) []grpc.ServerOption {
	return []grpc.ServerOption{
		grpc.ChainUnaryInterceptor(func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
			if err := a.authorizeContext(ctx, permission(info.FullMethod)); err != nil {
				return nil, err
			}
			return handler(ctx, req)
		}),
		grpc.ChainStreamInterceptor(func(srv any, ss grpc.ServerStream, info *grpc.StreamServerInfo, handler grpc.StreamHandler) error {
			if err := a.authorizeContext(ss.Context(), permission(info.FullMethod)); err != nil {
				return err
			}
			return handler(srv, ss)
		}),
	}
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
	return fmt.Sprintf("anonymous=%s tokens=%v", anonymous, names)
}
