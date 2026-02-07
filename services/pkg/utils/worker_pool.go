package utils

import (
	"runtime"
	"sync"
)

type WorkerPool struct {
	workerCount int
	tasks       chan func()
	done        chan struct{}
	wg          sync.WaitGroup
}

func NewWorkerPool() *WorkerPool {
	workerCount := runtime.GOMAXPROCS(0)
	return &WorkerPool{
		workerCount: workerCount,
		tasks:       make(chan func(), workerCount),
		done:        make(chan struct{}),
	}
}

func (wp *WorkerPool) Start() {
	for i := 0; i < wp.workerCount; i++ {
		go func() {
			for {
				select {
				case task := <-wp.tasks:
					task()
					wp.wg.Done()
				case <-wp.done:
					return
				}
			}
		}()
	}
}

func (wp *WorkerPool) SubmitOrRun(task func()) {
	wp.wg.Add(1)
	select {
	case wp.tasks <- task:
	case <-wp.done:
		wp.wg.Done()
	default:
		task()
		wp.wg.Done()
	}
}

func (wp *WorkerPool) Stop() {
	close(wp.done)
}

func (wp *WorkerPool) Wait() {
	wp.wg.Wait()
}
