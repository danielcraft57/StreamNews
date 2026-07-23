import { bus } from '../core/bus.js';

/** WebSocket temps reel → EventBus. */
export function connectRealtime(path = '/ws') {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}${path}`;
    let socket = null;
    let closed = false;

    const connect = () => {
        socket = new WebSocket(url);
        socket.onopen = () => bus.emit('ws:open');
        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                bus.emit('ws:message', data);
                if (data?.type) bus.emit(`ws:${data.type}`, data);
            } catch (err) {
                console.error('WS parse', err);
            }
        };
        socket.onclose = () => {
            bus.emit('ws:close');
            if (!closed) setTimeout(connect, 5000);
        };
        socket.onerror = (err) => bus.emit('ws:error', err);
    };

    connect();
    return {
        close() {
            closed = true;
            socket?.close();
        },
        get socket() { return socket; },
    };
}
