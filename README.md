# mcp-dialux

Servidor MCP (Python, FastMCP, stdio) que permite a um agente operar o **DIALux evo** no Windows
para cálculos luminotécnicos: gerar a geometria dos ambientes, importar luminárias, distribuir
luminárias por iluminância alvo, calcular, exportar o relatório PDF e ler os resultados em JSON.

O DIALux não tem API pública. O servidor automatiza a interface via **UI Automation**
(pywinauto, backend `uia`): controles localizados por AutomationId/nome/tipo, nunca por
coordenada de tela; esperas sempre por condição; cada ação conferida lendo a interface de volta.

## Requisitos

- Windows, DIALux evo 14 (testado com 5.14.0.5), **interface em português**.
- **DIALux Pro (ou o complemento "Unlock Non-Members")** para importar LDT/IES de fabricantes que
  não são membros DIAL. A versão gratuita só aceita luminárias de membros.
- Login no DIALux ID feito uma vez com "Lembrar senha" (o servidor não digita senhas).
- Python 3.12 e [uv](https://docs.astral.sh/uv/).

## Instalação

```powershell
git clone https://github.com/rafaelcruzmartins/mcp-dialux
cd mcp-dialux
uv sync
uv run pytest tests/test_offline.py
```

Registro no Claude Desktop (`claude_desktop_config.json`, dentro de `mcpServers`):

```json
"dialux": {
  "command": "C:\\Users\\<você>\\.local\\bin\\uv.exe",
  "args": ["--directory", "C:\\caminho\\para\\mcp-dialux", "run", "dialux-mcp-server"]
}
```

Variáveis opcionais: `DIALUX_EXE` (caminho do executável) e `DIALUX_MCP_LOG_DIR`
(padrão `~/.dialux-mcp/logs`; cada ação da interface é registrada em `dialux-mcp.log`).

## Ferramentas

| Ferramenta | O que faz | Verificação |
|---|---|---|
| `dialux_status` | DIALux aberto?, versão, projeto ativo, alterações não salvas, login, modal aberto | — |
| `dialux_open` | Abre o DIALux e, opcionalmente, um `.evo` | título da janela |
| `dialux_new` | Projeto vazio | projeto carregado |
| `dialux_save_as` | Salva em **novo** `.evo` (recusa se existir) | arquivo gravado + título |
| `stf_generate` | JSON de ambientes → `.stf` (STF 1.0.5) | validação do polígono |
| `dialux_import_stf` | Importa o STF como projeto novo; corrige pé-direito e refletâncias por ambiente | ambientes, pé-direito, plano de trabalho e FM lidos na interface |
| `dialux_import_ifc` | Importa um IFC (ex.: do Revit) como projeto novo, um ambiente por `IfcSpace`; método novo/legado, refletâncias do IFC ou padrão, plano de trabalho, nomes simplificados | nº de ambientes = nº de `IfcSpace`; pé-direito, plano de trabalho e FM lidos na interface |
| `dialux_set_room` | Altera nome, pé-direito, plano de trabalho e zona marginal de um ambiente | cada valor relido do painel redesenhado |
| `dialux_set_reflectances` | Teto/paredes/piso de um ambiente | campos lidos; conferir no relatório |
| `dialux_import_luminaire` | Importa LDT/IES e ativa a luminária | item no catálogo |
| `dialux_place_luminaires` | Distribuição automática em campo por ambiente: `target_lux` **ou** `count_x`/`count_y`; `mounting_height` | ambiente do arranjo, quantidade, alvo |
| `dialux_set_maintenance_factor` | FM fixo (todos ou alguns ambientes) | valor lido por ambiente |
| `dialux_calculate` | Calcula tudo e espera | fim do cálculo; erro se o DIALux registrar falha |
| `dialux_export_report` | Documentação completa → PDF (arquivo novo) | arquivo gravado |
| `report_read` | PDF → JSON por ambiente: Em, Emin, Emax, U0, g2, UGR, quantidade e potência das luminárias, área, alturas, FM, refletâncias | — |

JSON de entrada do `stf_generate` (comprimentos em metros, refletâncias em fração):

```json
{"name": "Exemplo 2 salas",
 "rooms": [
   {"name": "Sala A", "polygon": [[0,0],[6,0],[6,4],[0,4]], "height": 2.8, "working_plane": 0.75,
    "reflectances": {"ceiling": 0.73, "walls": 0.52, "floor": 0.21}, "maintenance_factor": 0.67},
   {"name": "Sala B", "polygon": [[6,0],[11,0],[11,4],[6,4]], "height": 3.0}]}
```

Fluxo típico: `stf_generate` → `dialux_import_stf` (com o mesmo JSON), ou `dialux_import_ifc` → `dialux_import_luminaire` →
`dialux_place_luminaires` (uma vez por ambiente) → `dialux_set_maintenance_factor` → `dialux_calculate` →
`dialux_export_report` → `report_read` → `dialux_save_as`.

## Teste ponta a ponta

Com o DIALux aberto e logado: `uv run python tests/live/e2e.py`. O teste chama as ferramentas pelo
protocolo MCP (2 salas, LDT genérico de `examples/luminarias`, 300 lx), lê o relatório e confere
contra o JSON de entrada. Saídas em `work/e2e-<data>/`.

## Limitações conhecidas

- **Só funciona com a interface em português** (alguns textos e nomes de nós da árvore são localizados,
  ex.: "Salas e espaços", "Plano de uso", "Resumo").
- **STF no evo 14:** um único pé-direito para todas as salas e refletâncias ignoradas. O servidor
  corrige o pé-direito e a refletância das **paredes** pela interface depois da importação.
- **Refletância de teto e piso não é automatizável:** no evo 14 teto e piso de ambientes vindos de STF são
  lajes do pavimento, e só se alteram pintando as superfícies na vista 3D (não acessível por UIA). Ficam no
  padrão do DIALux (70 % / 20 %); as ferramentas avisam quando o JSON pede outro valor. Paredes compartilhadas
  entre ambientes ficam com o último valor aplicado. Portas, janelas e luminárias do STF não são
  importadas pelo evo. Detalhes em [docs/stf-format.md](docs/stf-format.md).
- **LDT com `Isym=1`** (simetria rotacional compacta) faz o cálculo do evo 14 falhar. O gerador
  `scripts/make_generic_ldt.py` escreve a matriz completa.
- **Catálogo de luminárias:** a seleção é por nome; com nomes repetidos nos recentes usa-se o mais
  recente. Prefira nomes/códigos únicos.
- **UGR** só aparece no relatório quando o DIALux o calcula (coluna RUG); caso contrário é `null`.
- **IFC:** requer DIALux Pro. O pé-direito de cada ambiente vem do IFC (sem a limitação do STF). Os
  nomes chegam como "Name - LongName" (a ferramenta simplifica quando são iguais). IFC de teste em
  `examples/ifc/` (gerado por `scripts/make_test_ifc.py`); teste: `uv run python tests/live/e2e.py --ifc`.
- O servidor responde **Não** a "Guardar alterações?" e ao lembrete de autosave: alterações não salvas
  do projeto aberto são descartadas ao importar/abrir/criar. Use `dialux_save_as` antes.
- Uma operação por vez (a interface é única); não use o DIALux manualmente durante uma chamada.
- **Uso em segundo plano:** o DIALux precisa estar aberto, mas pode ficar atrás de outras janelas ou em
  outro monitor. O servidor não usa o teclado físico: os caminhos nos diálogos vão por mensagens
  `WM_CHAR` direto para o controle. Confirmar valores em campos do WPF exige mover o foco dentro do
  DIALux, então a janela dele pode vir para frente por um instante. Se estiver minimizada, é restaurada
  sem ativar no início de cada ferramenta.
- **Computador bloqueado:** com a sessão do Windows bloqueada o DIALux não aceita valores digitados (o foco
  não se move). As ferramentas detectam isso e param com erro pedindo para desbloquear. Valores de campos
  são sempre relidos do painel redesenhado; um valor que não foi gravado gera erro, nunca sucesso falso.
- A vista 3D/planta não é acessível por UIA; nada do fluxo depende dela.

Mapa dos controles da interface: [docs/ui-map.md](docs/ui-map.md).
