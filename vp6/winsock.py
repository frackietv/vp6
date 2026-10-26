"""TCP connections: the ``Winsock`` control, as VB's.

A Winsock (invisible at run time, like a Timer) is one end of a TCP
connection, or a server waiting for them::

    # a client
    self.wskClient.Connect("example.com", 80)

    def wskClient_Connect(self):                        # connected
        self.wskClient.SendData("GET / HTTP/1.0\\r\\n\\r\\n")

    def wskClient_DataArrival(self, BytesTotal):        # something came
        self.txtLog.SelText = self.wskClient.GetData()

    # a server: one Winsock listens, others (a control array) take the connections
    self.wskServer.LocalPort = 8000
    self.wskServer.Listen()

    def wskServer_ConnectionRequest(self, RequestID):
        Load(self.wskPeer, n)                           # (or self.wskPeer.Load(n))
        self.wskPeer[n].Accept(RequestID)

* ``Connect(RemoteHost, RemotePort)`` connects (the properties when left
  out): ``Connect`` fires once connected, ``Error(Number, Description)`` if
  it can't be.
* ``Listen()`` waits for connections on ``LocalPort`` (0: any free port,
  which LocalPort then tells), at the address ``Bind(LocalPort, LocalIP)``
  gave (``"127.0.0.1"``: from this computer only; every one without); each one fires ``ConnectionRequest
  (RequestID)``; ``Accept(RequestID)`` on this or another Winsock takes it
  (one not accepted by the end of the event is refused).
* ``SendData(Data)`` sends text (as UTF-8) or bytes; ``SendComplete`` fires
  when all of it has gone. ``DataArrival(BytesTotal)`` fires when data
  comes; ``GetData()`` takes it as text (``GetData(bytes)`` as bytes;
  ``MaxLen`` takes only that many bytes), ``PeekData`` leaves it there.
* ``Close()`` ends the connection (or stops listening); ``Close`` fires
  when the other end closes it. ``State`` (vpSckClosed, vpSckListening,
  vpSckConnecting, vpSckConnected...), ``RemoteHostIP``, ``LocalIP``,
  ``LocalHostName`` and ``BytesReceived`` tell how it is.
* A Winsock still connected when its form unloads is closed.
"""

from __future__ import annotations

import codecs
import itertools

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtNetwork import (QAbstractSocket, QHostAddress, QHostInfo, QNetworkInterface,
                               QTcpServer, QTcpSocket)
from PySide6.QtWidgets import QFrame, QLabel, QWidget

from ._props import P
from .controls import CONTROL_TYPES, EVENT_ARGS, Control

EVENT_ARGS.update({"ConnectionRequest": "RequestID", "Connect": "",
                   "DataArrival": "BytesTotal", "SendComplete": ""})

# Winsock.State (also in constants.py)
_CLOSED, _OPEN, _LISTENING, _PENDING_STATE, _RESOLVING, _RESOLVED, _CONNECTING, \
    _CONNECTED, _CLOSING, _ERROR = range(10)

# Error numbers, as VB's Winsock control gives them
_ERRORS = {
    QAbstractSocket.ConnectionRefusedError: 10061,
    QAbstractSocket.HostNotFoundError: 11001,
    QAbstractSocket.SocketTimeoutError: 10060,
    QAbstractSocket.AddressInUseError: 10048,
    QAbstractSocket.SocketAccessError: 10013,
    QAbstractSocket.NetworkError: 10050,
    QAbstractSocket.SocketAddressNotAvailableError: 10049,
}
_CONNECTION_RESET = 10054
_OTHER_ERROR = 40006  # (VB's "wrong protocol or connection state")

# Connections a server was asked for, not accepted yet: RequestID -> socket
_requests: dict[int, QTcpSocket] = {}
_request_ids = itertools.count(1)


class Winsock(Control):
    """A TCP connection or server (the module's documentation)."""

    TypeName = "Winsock"
    DefaultEvent = "DataArrival"
    DefaultSize = (32, 32)
    Events = ("ConnectionRequest", "Connect", "DataArrival", "SendComplete", "Close", "Error")
    EventArgs = {"Error": "Number, Description"}  # (a Process's Error: just Description)
    Properties = (
        P("Left", "int", 0, always=True, description="Position in the designer only"),
        P("Top", "int", 0, always=True, description="Position in the designer only"),
        P("RemoteHost", "str", "",
          description="The computer Connect connects to: a name or an IP address"),
        P("RemotePort", "int", 0, description="The port Connect connects to"),
        P("LocalPort", "int", 0,
          description="The port Listen waits on (0: any free one, which it then tells)"),
        P("Tag", "str", "", description="Free for your own use"),
    )

    def __init__(self, parent, Name: str = "", **props):
        self.__dict__.update(_server=None, _socket=None, _buffer=bytearray(), _failed=False,
                             _closing=False)
        super().__init__(parent, Name, **props)

    def _create_widget(self, parent):
        if self._design_mode:
            return _winsock_design_widget(parent)
        return None

    def _read_Width(self):
        return 32

    def _read_Height(self):
        return 32

    # -- what it is ------------------------------------------------------------------------------
    @property
    def State(self) -> int:
        """vpSckClosed, vpSckListening, vpSckResolvingHost, vpSckConnecting,
        vpSckConnected, vpSckClosing or vpSckError (until Close)."""
        if self._failed:
            return _ERROR
        if self._server is not None and self._server.isListening():
            return _LISTENING
        socket = self._socket
        if socket is None:
            return _CLOSED
        return {QAbstractSocket.HostLookupState: _RESOLVING,
                QAbstractSocket.ConnectingState: _CONNECTING,
                QAbstractSocket.ConnectedState: _CONNECTED,
                QAbstractSocket.BoundState: _OPEN,
                QAbstractSocket.ClosingState: _CLOSING}.get(socket.state(), _CLOSED)

    @property
    def RemoteHostIP(self) -> str:
        """The IP address of the computer at the other end ("" when not connected)."""
        socket = self._socket
        return socket.peerAddress().toString() if socket is not None else ""

    @property
    def LocalIP(self) -> str:
        """This computer's IP address: the connection's, else its first network one."""
        socket = self._socket
        if socket is not None and socket.state() == QAbstractSocket.ConnectedState:
            return socket.localAddress().toString()
        for address in QNetworkInterface.allAddresses():
            if address.protocol() == QAbstractSocket.IPv4Protocol and not address.isLoopback():
                return address.toString()
        return "127.0.0.1"

    @property
    def LocalHostName(self) -> str:
        """This computer's name."""
        return QHostInfo.localHostName()

    @property
    def BytesReceived(self) -> int:
        """How many bytes have come that GetData hasn't taken yet."""
        self._take_input()
        return len(self._buffer)

    # -- connecting ------------------------------------------------------------------------------
    def _need_closed(self, doing: str) -> None:
        if self.State not in (_CLOSED, _ERROR):
            raise RuntimeError(f"Winsock '{self.Name}' can't {doing}: it is in use "
                               f"(State {self.State}); Close it first")
        self.Close()

    def Connect(self, RemoteHost=None, RemotePort=None) -> None:
        """Connect to RemoteHost on RemotePort (the properties when left out;
        given, they are kept): Connect fires once connected, Error if not."""
        self._need_closed("connect")
        if RemoteHost is not None:
            self.RemoteHost = RemoteHost
        if RemotePort is not None:
            self.RemotePort = RemotePort
        host, port = self._values.get("RemoteHost", ""), int(self._values.get("RemotePort", 0))
        if not host or not 0 < port < 65536:
            raise ValueError(f"Winsock '{self.Name}': Connect needs a RemoteHost and a "
                             f"RemotePort (1-65535), not {host!r} and {port}")
        socket = QTcpSocket(self._form._widget)
        self._attach(socket)
        socket.connected.connect(lambda s=socket: s is self._socket and self._fire("Connect"))
        socket.connectToHost(host, port)

    def _attach(self, socket: QTcpSocket) -> None:
        self.__dict__.update(_socket=socket, _buffer=bytearray(), _failed=False)
        # (each checks it is still this Winsock's socket: a closed one may still signal)
        socket.readyRead.connect(lambda s=socket: s is self._socket and self._on_ready_read())
        socket.bytesWritten.connect(
            lambda _n, s=socket: s is self._socket and self._on_bytes_written())
        socket.disconnected.connect(
            lambda s=socket: s is self._socket and self._on_disconnected())
        socket.errorOccurred.connect(
            lambda error, s=socket: s is self._socket and self._on_error(error))

    def Bind(self, LocalPort=None, LocalIP=None) -> None:
        """The port (and the address: one of this computer's, e.g. "127.0.0.1"
        for connections from it only) Listen waits on; without a LocalIP,
        every address."""
        self._need_closed("bind")
        if LocalPort is not None:
            self._values["LocalPort"] = int(LocalPort)
        address = QHostAddress(str(LocalIP)) if LocalIP else None
        if address is not None and address.isNull():
            raise ValueError(f"Winsock '{self.Name}': {LocalIP!r} is not an address")
        self.__dict__["_bound"] = address

    def Listen(self) -> None:
        """Wait for connections on LocalPort (0: a free one, which LocalPort
        then is) at the address Bind gave (every one without); each fires
        ConnectionRequest(RequestID)."""
        self._need_closed("listen")
        server = QTcpServer(self._form._widget)
        address = self.__dict__.get("_bound") or QHostAddress(QHostAddress.Any)
        if not server.listen(address, int(self._values.get("LocalPort", 0))):
            number = _ERRORS.get(server.serverError(), _OTHER_ERROR)
            message = server.errorString()
            server.deleteLater()
            raise OSError(number, f"Winsock '{self.Name}' can't listen on port "
                                  f"{self._values.get('LocalPort', 0)}: {message}")
        self._values["LocalPort"] = int(server.serverPort())
        server.newConnection.connect(self._on_new_connection)
        self.__dict__.update(_server=server, _failed=False)

    def _on_new_connection(self) -> None:
        server = self._server
        while server is not None and server.hasPendingConnections():
            socket = server.nextPendingConnection()
            request = next(_request_ids)
            _requests[request] = socket
            try:
                self._fire("ConnectionRequest", request)
            finally:
                left = _requests.pop(request, None)
                if left is not None:  # (not accepted: refused)
                    left.abort()
                    left.deleteLater()

    def Accept(self, RequestID) -> None:
        """Take a connection a listening Winsock was asked for (in its
        ConnectionRequest): this Winsock is then connected to it."""
        socket = _requests.pop(int(RequestID), None)
        if socket is None:
            raise ValueError(f"Winsock '{self.Name}': no connection request {RequestID} "
                             "(accept it in the ConnectionRequest event)")
        if self._server is not None:  # (the listening one itself: it stops listening)
            self._server.close()
            self._server.deleteLater()
            self.__dict__["_server"] = None
        self._need_closed("accept a connection")
        socket.setParent(self._form._widget)
        self._attach(socket)
        self._values["RemotePort"] = int(socket.peerPort())
        self._values["RemoteHost"] = socket.peerAddress().toString()
        if socket.bytesAvailable():  # (sent before it was accepted)
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, socket, lambda s=socket: s is self._socket and
                              self._on_ready_read())

    def Close(self) -> None:
        """End the connection, or stop listening (no Close event: that one is
        for the other end closing it)."""
        socket, server = self._socket, self._server
        self.__dict__.update(_socket=None, _server=None, _failed=False, _closing=True)
        try:
            if socket is not None:
                if socket.state() == QAbstractSocket.ConnectedState and socket.bytesToWrite():
                    socket.disconnected.connect(socket.deleteLater)  # (what is left goes first)
                    socket.disconnectFromHost()
                else:
                    socket.abort()
                    socket.deleteLater()
            if server is not None:
                server.close()
                server.deleteLater()
        finally:
            self.__dict__["_closing"] = False

    # -- data ------------------------------------------------------------------------------------
    def SendData(self, Data) -> None:
        """Send text (as UTF-8) or bytes; SendComplete fires when it has all gone."""
        socket = self._socket
        if socket is None or socket.state() != QAbstractSocket.ConnectedState:
            raise RuntimeError(f"Winsock '{self.Name}' isn't connected (State {self.State})")
        data = bytes(Data) if isinstance(Data, (bytes, bytearray, memoryview)) else \
            str(Data).encode("utf-8")
        socket.write(data)

    def _take_input(self) -> None:
        socket = self._socket
        if socket is not None and socket.bytesAvailable():
            self._buffer.extend(bytes(socket.readAll()))

    def _on_ready_read(self) -> None:
        before = len(self._buffer)
        self._take_input()
        if len(self._buffer) > before:
            self._fire("DataArrival", len(self._buffer))

    def _on_bytes_written(self) -> None:
        socket = self._socket
        if socket is not None and not socket.bytesToWrite():
            self._fire("SendComplete")

    def _data(self, Type, MaxLen, take: bool):
        self._take_input()
        buffer = self._buffer
        size = len(buffer) if MaxLen is None or int(MaxLen) < 0 else min(int(MaxLen),
                                                                          len(buffer))
        chunk = bytes(buffer[:size])
        if Type is bytes or Type is bytearray:
            if take:
                del buffer[:size]
            return chunk
        if Type is not str:
            raise ValueError(f"Winsock '{self.Name}': GetData's Type is str or bytes, "
                             f"not {Type!r}")
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        text = decoder.decode(chunk)
        pending = len(decoder.getstate()[0])  # (a character not all here yet: left for later)
        if take:
            del buffer[:size - pending]
        return text

    def GetData(self, Type=str, MaxLen=None):
        """Take what has come: as text (decoded as UTF-8; a character not all
        here yet is left for later) or, ``GetData(bytes)``, as bytes; MaxLen
        takes only that many bytes."""
        return self._data(Type, MaxLen, take=True)

    def PeekData(self, Type=str, MaxLen=None):
        """What GetData would take, leaving it there."""
        return self._data(Type, MaxLen, take=False)

    # -- the other end ------------------------------------------------------------------------------
    def _on_disconnected(self) -> None:
        if not self._closing and self._socket is not None:
            self._take_input()
            self._fire("Close")

    def _on_error(self, error) -> None:
        if self._closing or self._socket is None:
            return
        if error == QAbstractSocket.RemoteHostClosedError:
            return  # (disconnected: Close)
        self.__dict__["_failed"] = True
        number = _ERRORS.get(error, _CONNECTION_RESET if error ==
                             QAbstractSocket.NetworkError else _OTHER_ERROR)
        self._fire("Error", number, self._socket.errorString())

    def _form_unloaded(self) -> None:
        """Its form unloads: the connection (or server) is closed."""
        self.Close()


def _winsock_design_widget(parent: QWidget) -> QLabel:
    """The icon the designer shows for a Winsock: two computers, connected."""
    pixmap = QPixmap(26, 26)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#333333"), 1.2))
    painter.setBrush(QColor("#5b9bd5"))
    painter.drawRect(2, 3, 9, 7)
    painter.drawRect(15, 16, 9, 7)
    painter.setPen(QPen(QColor("#2e7d32"), 1.6))
    painter.drawLine(6, 11, 6, 19)
    painter.drawLine(6, 19, 14, 19)
    painter.end()
    label = QLabel(parent)
    label.setFixedSize(32, 32)
    label.setAlignment(Qt.AlignCenter)
    label.setFrameStyle(QFrame.Panel | QFrame.Raised)
    label.setPixmap(pixmap)
    return label


# The Toolbox: after the other controls (Menu stays last)
CONTROL_TYPES["Winsock"] = Winsock
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")
