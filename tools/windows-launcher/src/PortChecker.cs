using System.Net;
using System.Net.Sockets;

namespace BioMatCAD.Launcher;

/// <summary>
/// Verifica ocupação real de portas TCP locais usando sockets reais (nunca "parsing" de
/// netstat/Get-NetTCPConnection, que variam entre plataformas). Uma porta é considerada "em uso"
/// se não for possível abrir um TcpListener nela em 127.0.0.1.
/// </summary>
public static class PortChecker
{
    public static bool IsPortInUse(int port, IPAddress? address = null)
    {
        address ??= IPAddress.Loopback;
        var listener = new TcpListener(address, port);
        try
        {
            listener.Start();
            return false;
        }
        catch (SocketException)
        {
            return true;
        }
        finally
        {
            try { listener.Stop(); } catch { /* ignore */ }
        }
    }

    /// <summary>
    /// Espera até que uma porta comece a aceitar conexões TCP (serviço ficou pronto), com timeout.
    /// Usado para "aguardar os serviços ficarem disponíveis" antes de abrir o navegador.
    /// </summary>
    public static bool WaitUntilReady(int port, TimeSpan timeout, TimeSpan? pollInterval = null, IPAddress? address = null)
    {
        address ??= IPAddress.Loopback;
        pollInterval ??= TimeSpan.FromMilliseconds(500);
        var deadline = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < deadline)
        {
            try
            {
                using var client = new TcpClient();
                var connectTask = client.ConnectAsync(address, port);
                if (connectTask.Wait(TimeSpan.FromMilliseconds(300)) && client.Connected)
                {
                    return true;
                }
            }
            catch
            {
                // ainda não está pronto -- continua tentando até o timeout
            }
            Thread.Sleep(pollInterval.Value);
        }
        return false;
    }
}
