package utils

import (
	"errors"
	"net/url"
)

func ParseHttpUrl(urlstr string) (string, error) {
	uri, err := url.Parse(urlstr)
	if err != nil {
		return "", err
	}

	port := uri.Port()
	if port == "" {
		uri.Host += ":8080"
	}

	var httpUri string
	switch uri.Scheme {
	case "tcp":
		httpUri = uri.Host

	default:
		return "", errors.New("Unsupported protocol: " + uri.Scheme)
	}

	return httpUri, nil
}

// Parses a string of the form <scheme>://<host>:<port> and returns the
// host and port as a string, or an error if the string is not a valid URL.
// If the port is not specified, it defaults to 9090.
// The scheme must be "tcp".
func ParseGrpcUrl(urlstr string) (string, error) {
	uri, err := url.Parse(urlstr)
	if err != nil {
		return "", err
	}

	port := uri.Port()
	if port == "" {
		uri.Host += ":9090"
	}

	var grpcUri string
	switch uri.Scheme {
	case "tcp":
		grpcUri = uri.Host

	// These are not yet supported by the Go implementation of gRPC,
	// but are valid in the gRPC c-core implementation.
	// https://github.com/grpc/grpc/blob/master/doc/naming.md#name-syntax
	//
	// case "tcp4":
	// 	grpcUri = "ipv4:" + uri.Host + ":" + port
	//
	// case "tcp6":
	// 	grpcUri = "ipv6:" + uri.Host + ":" + port
	//
	// case "unix":
	// 	grpcUri = fmt.Sprintf("uds://%s", uri.Path)

	default:
		return "", errors.New("Unsupported protocol: " + uri.Scheme)
	}

	return grpcUri, nil
}
