package worker

import (
	"compress/gzip"
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/srand/jolt/scheduler/pkg/log"
	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/scheduler"
	"github.com/srand/jolt/scheduler/pkg/utils"
	"google.golang.org/protobuf/proto"
)

type worker struct {
	builds   chan *protocol.BuildRequest
	client   protocol.WorkerClient
	config   *WorkerConfig
	platform *scheduler.Platform
}

func NewWorker(platform *scheduler.Platform, client protocol.WorkerClient, config *WorkerConfig) *worker {
	return &worker{
		client:   client,
		config:   config,
		platform: platform,
	}
}

func (w *worker) Run() {
	log.Info("Starting")

	for {
		if err := w.run(); err != nil {
			log.Debug(err)
			time.Sleep(time.Second)
			continue
		}
		break
	}
	log.Info("Terminating")
}

func (w *worker) run() error {
	ctx := context.Background()
	stream, err := w.client.GetInstructions(ctx)
	if err != nil {
		return err
	}
	defer stream.CloseSend()

	reply := func(status protocol.WorkerUpdate_Status, err error) error {
		var update *protocol.WorkerUpdate

		if err != nil {
			if detailedErr, ok := err.(utils.DetailedError); ok {
				update = &protocol.WorkerUpdate{
					Status: status,
					Error: &protocol.WorkerError{
						Message: detailedErr.Error(),
						Details: detailedErr.Details(),
					},
				}
			} else {
				update = &protocol.WorkerUpdate{
					Status: status,
					Error: &protocol.WorkerError{
						Message: err.Error(),
					},
				}
			}
		} else {
			update = &protocol.WorkerUpdate{
				Status: status,
			}
		}

		return stream.Send(update)
	}

	log.Debug("Connected to scheduler")

	err = w.enlist(stream)
	if err != nil {
		return err
	}

	requests := make(chan *protocol.WorkerRequest)
	go func() {
		defer close(requests)
		for {
			request, err := stream.Recv()
			if err == io.EOF {
			}
			if err != nil {
				log.Debug(err)
				return
			}

			requests <- request
		}
	}()

	var currentCmd chan error
	var currentProc *os.Process
	var currentBuildFile string
	// var currentBuild *protocol.BuildRequest

	for {
		select {
		case request := <-requests:
			if request == nil {
				return errors.New("read error")
			}
			switch request.Action {
			case protocol.WorkerRequest_BUILD:
				log.Info("Accepted new build request:", request.BuildId)
				if currentCmd != nil {
					continue
				}

				currentBuildFile, err = w.writeBuildRequest(request.Build)
				if err != nil {
					panic(err)
				}

				log.Info("Deploying client", request.Build.Environment.Client)
				digest, err := w.deployClient(request.Build.Environment.Client)
				if err != nil {
					log.Error("Failed to deploy client:", err)
					reply(protocol.WorkerUpdate_DEPLOY_FAILED, err)
					os.RemoveAll(currentBuildFile)
					continue
				}

				currentCmd, currentProc, err = w.startExecutor(digest, request.WorkerId, request.BuildId, currentBuildFile)
				if err != nil {
					reply(protocol.WorkerUpdate_EXECUTOR_FAILED, err)
					os.RemoveAll(currentBuildFile)
					currentCmd = nil
					currentProc = nil
					continue
				}

			case protocol.WorkerRequest_CANCEL_BUILD:
				log.Info("Sending interrupt signal to executor:", request.BuildId)
				if currentProc != nil {
					err = currentProc.Signal(os.Interrupt)
					if err != nil {
						log.Debug(err)
					}
				}

			default:
				log.Info("Received unknown action request:", request.Action)
				continue
			}

		case err := <-currentCmd:
			if err != nil && !strings.Contains(err.Error(), "signal: interrupt") {
				log.Info("Executor terminated with error:", err.Error())
				err = reply(protocol.WorkerUpdate_EXECUTOR_FAILED, err)
			} else {
				log.Info("Executor terminated")
				err = reply(protocol.WorkerUpdate_BUILD_ENDED, nil)
			}

			os.Remove(currentBuildFile)
			currentCmd = nil
			currentProc = nil
			currentBuildFile = ""

			if err != nil {
				return err
			}
		}
	}
}

// Serialize a BuildRequest pb to a temporary file so that the executor can read it
func (w *worker) writeBuildRequest(request *protocol.BuildRequest) (string, error) {
	out, err := proto.Marshal(request)
	if err != nil {
		return "", err
	}

	file, err := os.CreateTemp("", "jolt-build-")
	if err != nil {
		return "", err
	}

	_, err = file.Write(out)
	if err != nil {
		file.Close()
		os.Remove(file.Name())
		return "", err
	}

	file.Close()
	return file.Name(), nil
}

func (w *worker) deployClient(client *protocol.Client) (string, error) {
	if client == nil {
		return "", errors.New("Client information is missing")
	}

	digest, err := utils.Sha1String(client.String())
	if err != nil {
		return "", err
	}

	deployPath := w.deployPath(digest)

	venv := w.vEnvPath(digest)
	if _, err := os.Stat(venv); err == nil {
		if err := w.runClient(digest, "jolt", "--version"); err == nil {
			return digest, nil
		} else {
			os.RemoveAll(deployPath)
		}
	}

	os.RemoveAll(deployPath)
	err = os.MkdirAll(deployPath, 0777)
	if err != nil {
		os.RemoveAll(deployPath)
		return "", err
	}

	err = utils.RunWait("virtualenv", venv)
	if err != nil {
		os.RemoveAll(deployPath)
		return "", err
	}

	err = w.runClient(digest, "pip", "install", "--upgrade", "pip")
	if err != nil {
		os.RemoveAll(deployPath)
		return "", err
	}

	if (client.Identity != "" && w.config.CacheUri != "") || client.Url != "" {
		var url string = client.Url

		if url == "" {
			url = fmt.Sprintf("%s/jolt/main@%s.tar.gz", w.config.CacheUri, client.Identity)
		}

		log.Info("Deploying client from URL:", url)

		response, err := http.Get(url)
		if err != nil {
			os.RemoveAll(deployPath)
			return "", err
		}
		defer response.Body.Close()

		if response.StatusCode >= 400 {
			return "", errors.New(response.Status)
		}

		srcPath := filepath.Join(deployPath, "src")
		err = os.MkdirAll(srcPath, 0777)
		if err != nil {
			os.RemoveAll(deployPath)
			return "", err
		}

		var reader io.Reader = response.Body

		switch {
		case strings.HasSuffix(url, ".tar.gz"), strings.HasSuffix(url, ".tgz"):
			reader, err = gzip.NewReader(reader)
			if err != nil {
				os.RemoveAll(deployPath)
				return "", err
			}
			fallthrough

		case strings.HasSuffix(url, ".tar"):
			err = utils.Untar(reader, srcPath)
			if err != nil {
				os.RemoveAll(deployPath)
				return "", err
			}

		default:
			log.Fatal("Unsupported file extension:", url)
		}

		err = w.runClient(digest, "pip", "install", srcPath)
		if err != nil {
			os.RemoveAll(deployPath)
			return "", err
		}
	} else {
		log.Info("Deploying client from the Python Package Index:", client.Version)

		args := append([]string{"pip", "install", "jolt==" + client.Version}, client.Requirements...)
		err = w.runClient(digest, args...)
		if err != nil {
			os.RemoveAll(deployPath)
			return "", err
		}
	}

	return digest, nil
}

func (w *worker) deployPath(digest string) string {
	return filepath.Join("build", "selfdeploy", digest)
}

func (w *worker) vEnvPath(digest string) string {
	return filepath.Join(w.deployPath(digest), "env")
}

func (w *worker) activateVEnvPath(digest string) string {
	return filepath.Join(w.vEnvPath(digest), "bin", "activate")
}

func (w *worker) runClient(digest string, args ...string) error {
	activate := w.activateVEnvPath(digest)

	envargs := []string{"sh", "-c", fmt.Sprintf(". %s && %s", activate, strings.Join(args, " "))}
	args = append(envargs, args...)
	return utils.RunWait(envargs...)
}

func (w *worker) startExecutor(digest, worker, build, request string) (chan error, *os.Process, error) {
	activate := w.activateVEnvPath(digest)

	args := []string{"jolt", "-vv", "executor", "-w", worker, "-b", build, request}
	envargs := []string{"sh", "-c", fmt.Sprintf(". %s && %s", activate, strings.Join(args, " "))}

	return utils.Run(envargs...)
}

func (w *worker) enlist(stream protocol.Worker_GetInstructionsClient) error {
	update := &protocol.WorkerUpdate{
		Status:   protocol.WorkerUpdate_ENLISTING,
		Platform: (*protocol.Platform)(w.platform),
	}
	return stream.Send(update)
}
