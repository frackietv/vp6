"""The Winsock control: a TCP server (Listen, ConnectionRequest, Accept on another
Winsock), a client (Connect), sending and receiving (SendData, DataArrival,
GetData, PeekData, SendComplete), closing (Close, the Close event), errors
and State; in the IDE (the Toolbox, the designer)."""

import os

import pytest

from conftest import wait_for
from vp6 import (ControlArray, Form, Load, Winsock, vpSckClosed, vpSckConnected,
                 vpSckConnectionRefused, vpSckError, vpSckListening)
from vp6.controls import CONTROL_TYPES, EVENT_ARGS

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class Chat(Form):
    def InitializeComponent(self):
        self.wskServer = Winsock(self)
        self.wskPeer = ControlArray()
        self.wskPeer[0] = Winsock(self)
        self.wskClient = Winsock(self, RemoteHost="127.0.0.1")
        self.log = []

    def wskServer_ConnectionRequest(self, RequestID):
        self.log.append(("request", self.wskServer.State))
        index = len(self.wskPeer)
        Load(self.wskPeer, index)
        self.wskPeer[index].Accept(RequestID)

    def wskPeer_DataArrival(self, Index, BytesTotal):
        text = self.wskPeer[Index].GetData()
        self.log.append(("server got", Index, text))
        self.wskPeer[Index].SendData(text.upper())

    def wskPeer_Close(self, Index):
        self.log.append(("peer closed", Index))

    def wskClient_Connect(self):
        self.log.append("connected")

    def wskClient_DataArrival(self, BytesTotal):
        self.log.append(("client has", BytesTotal))

    def wskClient_SendComplete(self):
        self.log.append("sent")

    def wskClient_Close(self):
        self.log.append("client closed")

    def wskClient_Error(self, Number, Description):
        self.log.append(("error", Number))


@pytest.fixture
def chat(qapp):
    form = Chat()
    form.Show()
    yield form
    form.Unload()


def test_a_server_and_a_client(chat):
    server, client = chat.wskServer, chat.wskClient
    assert server.State == vpSckClosed and client.BytesReceived == 0
    server.Listen()  # (LocalPort 0: any free port, which it then tells)
    assert server.State == vpSckListening and server.LocalPort > 0
    client.Connect(RemotePort=server.LocalPort)
    wait_for(lambda: "connected" in chat.log and len(chat.wskPeer) == 2)
    assert client.State == vpSckConnected and client.RemoteHostIP == "127.0.0.1"
    assert ("request", vpSckListening) in chat.log and server.State == vpSckListening
    peer = chat.wskPeer[1]
    assert peer.State == vpSckConnected and peer.RemotePort > 0
    client.SendData("héllo")
    wait_for(lambda: ("client has", 6) in chat.log)
    assert ("server got", 1, "héllo") in chat.log and "sent" in chat.log
    assert client.PeekData() == "HÉLLO" and client.BytesReceived == 6
    assert client.GetData(str, 2) == "H"  # (half a character: left for later)
    assert client.BytesReceived == 5 and client.GetData(bytes, 1) == b"\xc3"
    assert client.GetData(bytes) == b"\x89LLO" and client.BytesReceived == 0
    client.SendData(b"\x00bytes")
    wait_for(lambda: any(e[:2] == ("server got", 1) and "bytes" in e[2] for e in chat.log
                         if isinstance(e, tuple)))
    peer.Close()  # this end: no Close event here; the other end gets one
    wait_for(lambda: "client closed" in chat.log)
    assert ("peer closed", 1) not in chat.log and peer.State == vpSckClosed
    server.Close()
    assert server.State == vpSckClosed


def test_a_refused_connection_and_mistakes(chat):
    server = chat.wskServer
    server.Listen()
    port = server.LocalPort
    server.Close()  # (nobody listens there now)
    client = chat.wskClient
    client.Connect("127.0.0.1", port)
    wait_for(lambda: any(isinstance(e, tuple) and e[0] == "error" for e in chat.log))
    assert ("error", vpSckConnectionRefused) in chat.log and client.State == vpSckError
    client.Close()
    assert client.State == vpSckClosed
    with pytest.raises(RuntimeError, match="isn't connected"):
        client.SendData("x")
    with pytest.raises(ValueError, match="no connection request"):
        client.Accept(12345)
    with pytest.raises(ValueError, match="RemotePort"):
        client.Connect("127.0.0.1", 0)
    server.Listen()
    with pytest.raises(RuntimeError, match="in use"):
        server.Listen()
    with pytest.raises(ValueError, match="str or bytes"):
        client.GetData(int)
    assert client.LocalHostName and client.LocalIP


def test_a_request_not_accepted_is_refused(qapp):
    class Refuses(Form):
        def InitializeComponent(self):
            self.wskServer = Winsock(self)
            self.wskClient = Winsock(self)
            self.requests = []
            self.closed = []

        def wskServer_ConnectionRequest(self, RequestID):
            self.requests.append(RequestID)

        def wskClient_Close(self):
            self.closed.append(True)

    form = Refuses()
    form.wskServer.Listen()
    form.wskClient.Connect("127.0.0.1", form.wskServer.LocalPort)
    wait_for(lambda: form.requests and form.closed)
    form.Unload()
    assert form.wskServer.State == vpSckClosed and form.wskClient.State == vpSckClosed


def test_in_the_ide(qapp):
    assert CONTROL_TYPES["Winsock"] is Winsock and list(CONTROL_TYPES)[-1] == "Menu"
    assert Winsock.EventArgs["Error"] == "Number, Description"
    assert EVENT_ARGS["Error"] == "Description"  # (a Process's)
    assert EVENT_ARGS["ConnectionRequest"] == "RequestID"
    from vp6.ide.icons import icon
    from vp6.ide.panels import Toolbox

    assert "Winsock" in Toolbox().buttons and not icon("Winsock").isNull()
    form = Chat()
    assert form.wskClient._widget is None  # (invisible at run time)
    form._widget.close()
