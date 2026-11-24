# Eletrozone NetScan — Scanner de Rede

Aplicativo desktop para Windows desenvolvido com a identidade visual **Eletrozone — Segurança Eletrônica**, para descoberta rápida de dispositivos conectados na rede local ou em pools de IP personalizados.

## Funcionalidades

- **Descoberta completa de IPs ativos na rede**: combina ARP nativo do Windows (`SendARP`) com ICMP (`IcmpSendEcho`) em paralelo para localizar hosts mesmo com firewall bloqueando ping.
- **Seleção flexível de pool**:
  - Detecção automática das interfaces de rede ativas do Windows (Ethernet, Wi-Fi, VPN).
  - Modo **Sub-rede (CIDR)** (ex.: `192.168.1.0/24`, `10.0.0.0/24`, `10.0.0.0/20`) com atalhos rápidos.
  - Modo **Faixa de IP (Início — Fim)** para consultar exatamente o pool desejado (ex.: `192.168.1.50` até `192.168.1.150`).
- **Informações detalhadas na consulta**:
  - **Endereço IP** (com marcação automática de `[ESTE PC]` e `[GW]`)
  - **Hostname** (DNS Reverso + consulta NetBIOS UDP/137)
  - **Endereço MAC**
  - **Fabricante** (base OUI integrada com foco em CFTV/infraestrutura como Intelbras, Hikvision, Dahua, Ubiquiti, MikroTik, TP-Link, Dell, HP, Apple, Samsung, Xiaomi, Espressif, etc.)
  - **Tipo de Conexão (`Wi-Fi` ou `Cabeado`)**: detecção exata para o adaptador local e classificação inteligente multi-sinal (MAC aleatório Wi-Fi, hostname, fabricante OUI, serviços de rede/CFTV e perfil de latência) com explicação do critério ao passar o mouse.
  - **Latência (ms)**
- **Ações rápidas**: busca/filtro em tempo real, filtro por Cabeado/Wi-Fi, menu de contexto (copiar IP/MAC/Hostname ou abrir `http://` / `https://` direto no navegador) e exportação para **CSV**.

## Como executar

### Executável pronto (Windows)
Execute diretamente:
```
dist/EletrozoneNetScan.exe
```

### A partir do código-fonte
```powershell
pip install -r requirements.txt
python main.py
```

### Recompilar o executável `.exe`
```powershell
powershell -ExecutionPolicy Bypass -File build_exe.ps1
```
