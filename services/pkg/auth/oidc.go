package auth

import (
	"context"
	"errors"
	"fmt"
	"slices"
	"strings"
	"sync"

	"github.com/coreos/go-oidc/v3/oidc"
	"github.com/srand/jolt/scheduler/pkg/log"
)

// Permissions granted to the members of a group of an OpenID Connect provider.
type Group struct {
	// Name of the group, as in the groups claim of tokens.
	Name string `mapstructure:"name"`
	// Permissions granted to the members of the group.
	Permissions []Permission `mapstructure:"permissions"`
}

// Configuration of tokens issued by an OpenID Connect provider, such as
// Keycloak or Dex in front of LDAP.
type OIDCConfig struct {
	// URL of the provider, which publishes its configuration and keys at
	// <issuer>/.well-known/openid-configuration.
	Issuer string `mapstructure:"issuer"`
	// Audience that tokens must be issued to, normally the client ID that
	// Jolt signs in with.
	Audience string `mapstructure:"audience"`
	// Claim with the name of the user, used in logs. Default: preferred_username.
	NameClaim string `mapstructure:"name_claim"`
	// Claim with the groups of the user, a list or a single string. Nested
	// claims are separated by dots, such as realm_access.roles. Default: groups.
	GroupsClaim string `mapstructure:"groups_claim"`
	// Permissions of all users of the provider.
	Permissions []Permission `mapstructure:"permissions"`
	// Permissions of the members of groups.
	Groups []Group `mapstructure:"groups"`
}

// Verifies tokens issued by an OpenID Connect provider. The configuration
// of the provider is fetched on first use, so that services start while the
// provider is unavailable.
type oidcVerifier struct {
	config   OIDCConfig
	mutex    sync.Mutex
	verifier *oidc.IDTokenVerifier
}

func newOIDCVerifier(config OIDCConfig) (*oidcVerifier, error) {
	if config.Issuer == "" {
		return nil, errors.New("the issuer of OIDC tokens is not configured")
	}
	if config.Audience == "" {
		return nil, errors.New("the audience of OIDC tokens is not configured")
	}
	if config.NameClaim == "" {
		config.NameClaim = "preferred_username"
	}
	if config.GroupsClaim == "" {
		config.GroupsClaim = "groups"
	}
	return &oidcVerifier{config: config}, nil
}

func (v *oidcVerifier) getVerifier(ctx context.Context) (*oidc.IDTokenVerifier, error) {
	v.mutex.Lock()
	defer v.mutex.Unlock()

	if v.verifier == nil {
		// The provider keeps using the context to fetch new keys
		provider, err := oidc.NewProvider(context.WithoutCancel(ctx), v.config.Issuer)
		if err != nil {
			return nil, err
		}
		v.verifier = provider.Verifier(&oidc.Config{ClientID: v.config.Audience})
	}
	return v.verifier, nil
}

// identities returns the identities that the configuration may grant, to
// validate their permissions.
func (v *oidcVerifier) identities() []Identity {
	identities := []Identity{{Name: "OIDC users", Permissions: v.config.Permissions}}
	for _, group := range v.config.Groups {
		identities = append(identities, Identity{Name: "OIDC group " + group.Name, Permissions: group.Permissions})
	}
	return identities
}

// Verify returns the user of a token signed by the provider.
func (v *oidcVerifier) Verify(ctx context.Context, token string) (*Identity, error) {
	verifier, err := v.getVerifier(ctx)
	if err != nil {
		log.Error("Failed to get the configuration of OIDC provider", v.config.Issuer, ":", err)
		return nil, ErrUnauthenticated
	}

	idToken, err := verifier.Verify(ctx, token)
	if err != nil {
		log.Debug("Rejected OIDC token:", err)
		return nil, ErrUnauthenticated
	}

	claims := map[string]any{}
	if err := idToken.Claims(&claims); err != nil {
		return nil, ErrUnauthenticated
	}

	name, _ := claim(claims, v.config.NameClaim).(string)
	if name == "" {
		name = idToken.Subject
	}

	permissions := slices.Clone(v.config.Permissions)
	groups := stringList(claim(claims, v.config.GroupsClaim))
	for _, group := range v.config.Groups {
		if slices.Contains(groups, group.Name) {
			permissions = append(permissions, group.Permissions...)
		}
	}
	slices.Sort(permissions)

	return &Identity{Name: name, Permissions: slices.Compact(permissions)}, nil
}

// claim returns the value of a claim, which may be nested.
func claim(claims map[string]any, name string) any {
	var value any = claims
	for _, key := range strings.Split(name, ".") {
		object, ok := value.(map[string]any)
		if !ok {
			return nil
		}
		value = object[key]
	}
	return value
}

func stringList(value any) []string {
	switch value := value.(type) {
	case string:
		return []string{value}
	case []any:
		list := []string{}
		for _, item := range value {
			if s, ok := item.(string); ok {
				list = append(list, s)
			}
		}
		return list
	}
	return nil
}

func (c *OIDCConfig) String() string {
	groups := []string{}
	for _, group := range c.Groups {
		groups = append(groups, fmt.Sprintf("%s%v", group.Name, group.Permissions))
	}
	return fmt.Sprintf("issuer=%s audience=%s permissions=%v groups=%v", c.Issuer, c.Audience, c.Permissions, groups)
}
