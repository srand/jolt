package auth

import (
	"crypto/rand"
	"crypto/rsa"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/go-jose/go-jose/v4"
	"github.com/stretchr/testify/assert"
)

// A provider that publishes its configuration and keys, and signs tokens.
type testProvider struct {
	server *httptest.Server
	key    *rsa.PrivateKey
}

func newTestProvider(t *testing.T) *testProvider {
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	assert.NoError(t, err)

	p := &testProvider{key: key}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /.well-known/openid-configuration", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{
			"issuer":                                p.server.URL,
			"jwks_uri":                              p.server.URL + "/keys",
			"id_token_signing_alg_values_supported": []string{"RS256"},
		})
	})
	mux.HandleFunc("GET /keys", func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(jose.JSONWebKeySet{Keys: []jose.JSONWebKey{
			{Key: &key.PublicKey, KeyID: "test", Algorithm: "RS256", Use: "sig"},
		}})
	})
	p.server = httptest.NewServer(mux)
	t.Cleanup(p.server.Close)
	return p
}

func (p *testProvider) sign(t *testing.T, key *rsa.PrivateKey, claims map[string]any) string {
	signer, err := jose.NewSigner(
		jose.SigningKey{Algorithm: jose.RS256, Key: key},
		(&jose.SignerOptions{}).WithHeader("kid", "test"))
	assert.NoError(t, err)
	payload, err := json.Marshal(claims)
	assert.NoError(t, err)
	signature, err := signer.Sign(payload)
	assert.NoError(t, err)
	token, err := signature.CompactSerialize()
	assert.NoError(t, err)
	return token
}

func (p *testProvider) token(t *testing.T, claims map[string]any) string {
	defaults := map[string]any{
		"iss": p.server.URL,
		"aud": "jolt",
		"sub": "1234",
		"exp": time.Now().Add(time.Hour).Unix(),
		"iat": time.Now().Unix(),
	}
	for key, value := range claims {
		defaults[key] = value
	}
	return p.sign(t, p.key, defaults)
}

func newOIDCAuthenticator(t *testing.T, p *testProvider) *Authenticator {
	a, err := New(Config{
		Tokens: []Token{
			{Name: "ci", Hash: HashToken("ci-token"), Permissions: []Permission{Read, Write}},
		},
		OIDC: &OIDCConfig{
			Issuer:      p.server.URL,
			Audience:    "jolt",
			Permissions: []Permission{Read},
			Groups: []Group{
				{Name: "Uploaders", Permissions: []Permission{Write}},
			},
		},
	}, Read, Write)
	assert.NoError(t, err)
	return a
}

func TestOIDCPermissionsOfGroups(t *testing.T) {
	p := newTestProvider(t)
	a := newOIDCAuthenticator(t, p)

	identity, err := a.Authorize(ctx, p.token(t, map[string]any{"preferred_username": "alice"}), Read)
	assert.NoError(t, err)
	assert.Equal(t, "alice", identity.Name)
	assert.Equal(t, []Permission{Read}, identity.Permissions)

	_, err = a.Authorize(ctx, p.token(t, map[string]any{"groups": []string{"Developers"}}), Write)
	assert.ErrorIs(t, err, ErrPermissionDenied)

	identity, err = a.Authorize(ctx, p.token(t, map[string]any{"groups": []string{"Developers", "Uploaders"}}), Write)
	assert.NoError(t, err)
	assert.Equal(t, "1234", identity.Name)
	assert.Equal(t, []Permission{Read, Write}, identity.Permissions)

	// Static tokens and anonymous clients are unchanged
	_, err = a.Authorize(ctx, "ci-token", Write)
	assert.NoError(t, err)
	_, err = a.Authorize(ctx, "", Read)
	assert.ErrorIs(t, err, ErrUnauthenticated)
}

func TestOIDCRejectsInvalidTokens(t *testing.T) {
	p := newTestProvider(t)
	a := newOIDCAuthenticator(t, p)

	otherKey, err := rsa.GenerateKey(rand.Reader, 2048)
	assert.NoError(t, err)

	invalid := map[string]string{
		"expired":        p.token(t, map[string]any{"exp": time.Now().Add(-time.Minute).Unix()}),
		"other audience": p.token(t, map[string]any{"aud": "other"}),
		"other issuer":   p.token(t, map[string]any{"iss": "https://other.example.com"}),
		"other key": p.sign(t, otherKey, map[string]any{
			"iss": p.server.URL, "aud": "jolt", "sub": "1234", "exp": time.Now().Add(time.Hour).Unix(),
		}),
		"not a JWT": "a.b.c",
	}
	for name, token := range invalid {
		_, err := a.Authorize(ctx, token, Read)
		assert.ErrorIs(t, err, ErrUnauthenticated, name)
	}
}

func TestOIDCNestedGroupsClaim(t *testing.T) {
	p := newTestProvider(t)
	a, err := New(Config{
		OIDC: &OIDCConfig{
			Issuer:      p.server.URL,
			Audience:    "jolt",
			GroupsClaim: "realm_access.roles",
			Groups:      []Group{{Name: "jolt-ci", Permissions: []Permission{Read, Write}}},
		},
	}, Read, Write)
	assert.NoError(t, err)

	token := p.token(t, map[string]any{"realm_access": map[string]any{"roles": []string{"jolt-ci"}}})
	_, err = a.Authorize(ctx, token, Write)
	assert.NoError(t, err)

	_, err = a.Authorize(ctx, p.token(t, nil), Read)
	assert.ErrorIs(t, err, ErrPermissionDenied)
}

func TestOIDCUnavailableProvider(t *testing.T) {
	p := newTestProvider(t)
	a := newOIDCAuthenticator(t, p)
	token := p.token(t, nil)
	p.server.Close()

	_, err := a.Authorize(ctx, token, Read)
	assert.ErrorIs(t, err, ErrUnauthenticated)
}

func TestOIDCInvalidConfiguration(t *testing.T) {
	_, err := New(Config{OIDC: &OIDCConfig{Audience: "jolt"}}, Read)
	assert.Error(t, err)
	_, err = New(Config{OIDC: &OIDCConfig{Issuer: "https://idp"}}, Read)
	assert.Error(t, err)
	_, err = New(Config{OIDC: &OIDCConfig{
		Issuer: "https://idp", Audience: "jolt",
		Groups: []Group{{Name: "admins", Permissions: []Permission{"admin"}}},
	}}, Read)
	assert.Error(t, err)
}
