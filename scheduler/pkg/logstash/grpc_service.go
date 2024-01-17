package logstash

import (
	"io"

	"github.com/srand/jolt/scheduler/pkg/protocol"
	"github.com/srand/jolt/scheduler/pkg/utils"
)

type LogStashService struct {
	protocol.UnimplementedLogStashServer
	stash LogStash
}

// NewLogStashService creates a new LogStashService
func NewLogStashService(stash LogStash) *LogStashService {
	return &LogStashService{
		stash: stash,
	}
}

// ReadLog reads a log from the logstash server
func (s *LogStashService) ReadLog(req *protocol.ReadLogRequest, stream protocol.LogStash_ReadLogServer) error {
	reader, err := s.stash.Read(req.Id)
	if err != nil {
		return err
	}
	defer reader.Close()

	filteredReader := NewFilteredLogReader(reader)
	filteredReader.AddFilter(func(ll *protocol.LogLine) bool {
		if req.After == nil {
			return true
		}
		return ll.Time.AsTime().After(req.After.AsTime())
	})
	filteredReader.AddFilter(func(ll *protocol.LogLine) bool {
		if req.Before == nil {
			return true
		}
		return ll.Time.AsTime().Before(req.Before.AsTime())
	})

	for {
		line, err := filteredReader.ReadLine()
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return utils.GrpcError(err)
		}

		response := &protocol.ReadLogResponse{
			Id:       req.Id,
			Loglines: []*protocol.LogLine{line},
		}

		if err := stream.Send(response); err != nil {
			return err
		}
	}
}
