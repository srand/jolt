package log

import (
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"runtime/debug"
	"time"
)

type LogLevel string

const (
	FatalLevel    = "fatal"
	ErrorLevel    = "error"
	WarningLevel  = "warn"
	DebugLevel    = "debug"
	InfoLevel     = "info"
	TraceLevel    = "trace"
	DisabledLevel = "disabled"
)

var levelmap = map[LogLevel]int{
	TraceLevel:    5,
	DebugLevel:    4,
	InfoLevel:     3,
	WarningLevel:  2,
	ErrorLevel:    1,
	FatalLevel:    0,
	DisabledLevel: -1,
}

var logfFuncMap = map[LogLevel]func(msg string, args ...interface{}){
	TraceLevel:   Tracef,
	DebugLevel:   Debugf,
	InfoLevel:    Infof,
	WarningLevel: Warnf,
	ErrorLevel:   Errorf,
	FatalLevel:   Fatalf,
}

var logFuncMap = map[LogLevel]func(args ...interface{}){
	TraceLevel:   Trace,
	DebugLevel:   Debug,
	InfoLevel:    Info,
	WarningLevel: Warn,
	ErrorLevel:   Error,
	FatalLevel:   Fatal,
}

type logWrapper struct {
	log   log.Logger
	Level LogLevel
}

func (l *logWrapper) Printf(level LogLevel, format string, args ...any) {
	if !ShouldLog(level, l.Level) {
		return
	}
	l.Println(level, fmt.Sprintf(format, args...))
}

func (l *logWrapper) Println(level LogLevel, args ...any) {
	if !ShouldLog(level, l.Level) {
		return
	}
	ts := time.Now().Local()
	timeStr := fmt.Sprintf("%s.%03d", ts.Format("2006-01-02 15:04:05"), ts.Nanosecond()/1000000)
	levelStr := fmt.Sprintf("- %5s -", level)
	allArgs := []any{timeStr, levelStr}
	allArgs = append(allArgs, args...)
	l.log.Println(allArgs...)
}

var (
	stdoutLog logWrapper
	stderrLog logWrapper
)

func init() {
	stdoutLog = logWrapper{*log.New(os.Stdout, "", 0), InfoLevel}
	stderrLog = logWrapper{*log.New(os.Stderr, "", 0), InfoLevel}
}

func SetLevel(loglevel LogLevel) error {
	_, ok := levelmap[loglevel]
	if !ok {
		return fmt.Errorf("No such log level %s", loglevel)
	}

	stderrLog.Level = loglevel
	stdoutLog.Level = loglevel
	return nil
}

func ValidLogLevel(level LogLevel) bool {
	_, ok := levelmap[level]
	return ok
}

func ShouldLog(logLevel, enabled LogLevel) bool {
	if !ValidLogLevel(logLevel) || !ValidLogLevel(enabled) {
		return false
	}
	return levelmap[logLevel] <= levelmap[enabled]
}

func Log(level LogLevel, msg string, args ...interface{}) {
	if ValidLogLevel(level) {
		if len(args) > 0 {
			logfFuncMap[level](msg, args...)
		} else {
			logFuncMap[level](msg)
		}
	}
}

func Trace(args ...interface{}) {
	stdoutLog.Println(TraceLevel, args...)
}

func Debug(args ...interface{}) {
	stdoutLog.Println(DebugLevel, args...)
}

func Info(args ...interface{}) {
	stdoutLog.Println(InfoLevel, args...)
}

func Warn(args ...interface{}) {
	stderrLog.Println(WarningLevel, args...)
}

func Error(args ...interface{}) {
	stderrLog.Println(ErrorLevel, args...)
}

func Fatal(args ...interface{}) {
	stderrLog.Println(FatalLevel, args...)
	debug.PrintStack()
	os.Exit(1)
}

func Tracef(format string, args ...interface{}) {
	stdoutLog.Printf(TraceLevel, format, args...)
}

func Debugf(format string, args ...interface{}) {
	stdoutLog.Printf(DebugLevel, format, args...)
}

func Infof(format string, args ...interface{}) {
	stdoutLog.Printf(InfoLevel, format, args...)
}

func Warnf(format string, args ...interface{}) {
	stderrLog.Printf(WarningLevel, format, args...)
}

func Errorf(format string, args ...interface{}) {
	stderrLog.Printf(ErrorLevel, format, args...)
}

func Fatalf(format string, args ...interface{}) {
	stderrLog.Printf(FatalLevel, format, args...)
	debug.PrintStack()
	os.Exit(1)
}

type logger struct{}

func NewLogger() *log.Logger {
	return log.New(NewLogWriter(DebugLevel), "", 0)
}

type writeFunc func([]byte) (int, error)

func (fn writeFunc) Write(data []byte) (int, error) {
	return fn(data)
}

func NewLogWriter(level LogLevel) io.Writer {
	return writeFunc(func(data []byte) (int, error) {
		Log(level, "%s", data)
		return 0, nil
	})
}

func DebugError(err error) {
	indent := 1

	Debug(err.Error())

	for {
		if err = errors.Unwrap(err); err == nil {
			break
		}

		Debugf("| %d: %s", indent, err.Error())
		indent += 1
	}
}
