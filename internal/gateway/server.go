package gateway

import (
	"fmt"
	"log/slog"
	"net/http"

	"github.com/coder/websocket"
	"github.com/lixuanqun/voice-realtime/internal/config"
	"github.com/lixuanqun/voice-realtime/internal/providers"
	"github.com/lixuanqun/voice-realtime/internal/realtime"
	"github.com/lixuanqun/voice-realtime/internal/session"
)

// maxWebSocketMessageBytes bounds one client message. Realtime clients
// batch 0.5–1s of base64-encoded PCM16 per input_audio_buffer.append, which
// easily exceeds the library's 32 KiB default read limit (#9), so allow
// 1 MiB per message.
const maxWebSocketMessageBytes = 1 << 20 // 1 MiB

// Server is the HTTP/WebSocket gateway.
type Server struct {
	cfg *config.Config
	log *slog.Logger
	mux *http.ServeMux
}

// New creates a gateway server.
func New(cfg *config.Config, log *slog.Logger) *Server {
	if log == nil {
		log = slog.Default()
	}
	s := &Server{cfg: cfg, log: log, mux: http.NewServeMux()}
	s.mux.HandleFunc("/healthz", s.handleHealth)
	s.mux.HandleFunc("/v1/realtime", s.handleRealtime)
	s.mux.HandleFunc("/", s.handleIndex)
	return s
}

// Handler returns the root HTTP handler.
func (s *Server) Handler() http.Handler {
	return s.mux
}

func (s *Server) handleHealth(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("ok"))
}

func (s *Server) handleIndex(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	_, _ = fmt.Fprintf(w, "voice-realtime gateway\nproviders: %v\nconnect: ws://%s/v1/realtime?provider=zhipu&model=glm-realtime-flash\n", providers.List(), r.Host)
}

func (s *Server) handleRealtime(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	providerName := r.URL.Query().Get("provider")
	if providerName == "" {
		providerName = "zhipu"
	}
	model := r.URL.Query().Get("model")

	if err := s.cfg.ValidateProvider(providerName); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	p, err := providers.Get(providerName)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	conn, err := websocket.Accept(w, r, &websocket.AcceptOptions{
		InsecureSkipVerify: true,
	})
	if err != nil {
		s.log.Error("websocket accept failed", "err", err)
		return
	}
	conn.SetReadLimit(maxWebSocketMessageBytes)
	defer conn.Close(websocket.StatusInternalError, "handler exit")

	ctx := r.Context()
	sessionID := r.Header.Get("X-Session-Id")
	if sessionID == "" {
		sessionID = fmt.Sprintf("%s-%s", providerName, model)
	}
	sess := session.New(sessionID, providerName, model)

	upstream, err := p.Dial(ctx, providers.ConnectConfig{
		Model:  model,
		Config: s.cfg,
	})
	if err != nil {
		s.log.Error("upstream dial failed", "provider", providerName, "err", err)
		_ = conn.Write(ctx, websocket.MessageText, realtime.NewErrorEvent("upstream_dial_failed", err.Error()))
		conn.Close(websocket.StatusInternalError, "upstream dial failed")
		return
	}
	defer upstream.Close()

	s.log.Info("session started", "provider", providerName, "model", model, "session", sess.ID)

	errCh := make(chan error, 2)

	go func() {
		for {
			typ, data, err := conn.Read(ctx)
			if err != nil {
				errCh <- err
				return
			}
			if typ != websocket.MessageText {
				continue
			}
			if realtime.EventType(data) == realtime.EventResponseCancel {
				sess.Cancel()
			}
			if err := upstream.WriteClientEvent(ctx, data); err != nil {
				errCh <- err
				return
			}
		}
	}()

	go func() {
		for {
			data, err := upstream.ReadServerEvent(ctx)
			if err != nil {
				errCh <- err
				return
			}
			if sess.IsCancelled() && realtime.EventType(data) == realtime.EventResponseAudioDelta {
				continue
			}
			if err := conn.Write(ctx, websocket.MessageText, data); err != nil {
				errCh <- err
				return
			}
			if realtime.EventType(data) == realtime.EventResponseDone {
				sess.ResetCancel()
			}
		}
	}()

	<-errCh
	conn.Close(websocket.StatusNormalClosure, "session ended")
	s.log.Info("session ended", "provider", providerName, "session", sess.ID)
}
