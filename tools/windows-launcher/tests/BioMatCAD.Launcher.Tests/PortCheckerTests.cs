using System.Net;
using System.Net.Sockets;
using BioMatCAD.Launcher;
using Xunit;

namespace BioMatCAD.Launcher.Tests;

public class PortCheckerTests
{
    [Fact]
    public void IsPortInUse_ComPortaRealmenteOcupada_RetornaVerdadeiro()
    {
        // Ocupa uma porta de verdade com um TcpListener real antes de perguntar -- sem mocks,
        // sem parsing de netstat: sockets reais do SO.
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        try
        {
            Assert.True(PortChecker.IsPortInUse(port));
        }
        finally
        {
            listener.Stop();
        }
    }

    [Fact]
    public void IsPortInUse_ComPortaRealmenteLivre_RetornaFalso()
    {
        // Pede ao SO uma porta efêmera livre (porta 0), fecha o listener imediatamente, e
        // confirma que ela é relatada como livre logo em seguida.
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();

        Assert.False(PortChecker.IsPortInUse(port));
    }

    [Fact]
    public void WaitUntilReady_QuandoServicoSobeDentroDoTimeout_RetornaVerdadeiro()
    {
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        _ = Task.Run(() =>
        {
            using var client = listener.AcceptTcpClient();
        });

        try
        {
            var ready = PortChecker.WaitUntilReady(port, TimeSpan.FromSeconds(5), TimeSpan.FromMilliseconds(100));
            Assert.True(ready);
        }
        finally
        {
            listener.Stop();
        }
    }

    [Fact]
    public void WaitUntilReady_QuandoNadaEstaEscutando_RetornaFalsoAposTimeout()
    {
        var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop(); // ninguém escutando nessa porta

        var ready = PortChecker.WaitUntilReady(port, TimeSpan.FromMilliseconds(800), TimeSpan.FromMilliseconds(150));
        Assert.False(ready);
    }
}
