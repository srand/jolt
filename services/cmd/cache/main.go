package main

import (
	"net/http"

	"github.com/srand/jolt/scheduler/pkg/cache"
	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/utils"

	"github.com/spf13/afero"
	"github.com/spf13/cobra"
	"github.com/spf13/viper"
)

var config Config

var rootCmd = &cobra.Command{
	Use:   "jolt-cache",
	Short: "Remote filesystem cache server",
	PersistentPreRun: func(cmd *cobra.Command, args []string) {
		viper.SetConfigName("cache.yaml")
		viper.SetConfigType("yaml")
		viper.AddConfigPath("/etc/jolt/")
		viper.AddConfigPath("$HOME/.config/jolt")
		viper.SetEnvPrefix("jolt")
		viper.AutomaticEnv()

		err := viper.ReadInConfig()
		if err != nil {
			log.Warn(err)
		}

		if err := viper.Unmarshal(&config); err != nil {
			log.Fatal(err)
		}

		switch {
		case config.Verbosity >= 2:
			log.SetLevel(log.TraceLevel)
		case config.Verbosity >= 1:
			log.SetLevel(log.DebugLevel)
		}
		log.Info("Log verbosity:", log.GetLevel())
	},
	Run: func(cmd *cobra.Command, args []string) {
		var fs utils.Fs

		if config.Path == "memory" {
			log.Info("Using in-memory data storage")
			fs = afero.NewMemMapFs()
		} else {
			log.Info("Using disk data storage:", config.Path)

			os := afero.NewOsFs()

			// Create cache directory if it doesn't exist
			if err := os.MkdirAll(config.Path, 0777); err != nil {
				log.Fatal(err)
			}

			fs = afero.NewBasePathFs(os, config.Path)

		}

		lru, err := cache.NewLRUCache(fs, &config)
		if err != nil {
			log.Fatal(err)
		}

		handler := cache.NewHttpHandler(lru)

		if config.Listen == nil || len(config.Listen) == 0 {
			if config.Insecure {
				config.Listen = []string{"tcp://:8080"}
			} else {
				config.Listen = []string{"tcp://:8433"}
			}
		}

		for _, address := range config.Listen {
			address, err := utils.ParseHttpUrl(address)
			if err != nil {
				log.Fatal(err)
			}

			go func() {
				log.Info("Listening on", address)
				if config.Insecure {
					err = http.ListenAndServe(address, handler)
				} else {
					if config.Certificate == "" || config.PrivateKey == "" {
						log.Fatal("A TLS certificate and private key must be configured")
					}
					err = http.ListenAndServeTLS(address, config.Certificate, config.PrivateKey, handler)
				}
				if err != nil {
					log.Fatal(err)
				}
			}()
		}

		select {}
	},
}

func init() {
	rootCmd.Flags().StringP("cert", "c", "", "TLS server certificate file")
	rootCmd.Flags().StringP("cert-key", "k", "", "TLS private key file")
	rootCmd.Flags().StringP("expiration", "e", "", "Artifact expiration timeout in seconds.")
	rootCmd.Flags().BoolP("insecure", "i", false, "Don't use TLS")
	rootCmd.Flags().StringSliceP("listen-http", "l", nil, "Address and port to listen on (default :8080, :8443)")
	rootCmd.Flags().StringP("max-size", "s", "10GB", "Maximum size of the cache.")
	rootCmd.Flags().StringP("path", "p", "/data", "Path to cache storage on disk, or 'memory' to store files in memory.")
	rootCmd.Flags().CountP("verbose", "v", "Verbosity (repeatable)")

	viper.BindPFlag("cert", rootCmd.Flags().Lookup("cert"))
	viper.BindPFlag("cert_key", rootCmd.Flags().Lookup("cert-key"))
	viper.BindPFlag("expiration", rootCmd.Flags().Lookup("expiration"))
	viper.BindPFlag("insecure", rootCmd.Flags().Lookup("insecure"))
	viper.BindPFlag("listen_http", rootCmd.Flags().Lookup("listen-http"))
	viper.BindPFlag("max_size", rootCmd.Flags().Lookup("max-size"))
	viper.BindPFlag("path", rootCmd.Flags().Lookup("path"))
	viper.BindPFlag("verbosity", rootCmd.Flags().Lookup("verbose"))
}

func main() {
	if err := rootCmd.Execute(); err != nil {
		log.Fatal(err)
	}
}
