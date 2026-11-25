# Formato STF usado pelo gerador

A DIAL não publica a especificação do STF; ela é enviada sob pedido a fabricantes de CAD
(ver [STF - Data exchange](https://evo.support-en.dial.de/support/solutions/articles/9000073195-stf-data-exchange)
e [Data exchange between CAD programs and DIALux](https://dialux4.support-en.dial.de/support/solutions/articles/9000073210-data-exchange-between-cad-programs-and-dialux)).
O layout segue os exportadores públicos que importam no evo:

- [kmorin/STF-Exporter](https://github.com/kmorin/STF-Exporter) (Revit → STF, citado pela DIAL)
- [BHoM/DIALux_Toolkit](https://github.com/BHoM/DIALux_Toolkit)

Comum aos dois: `STFF=1.0.5`, seções `[VERSION]`, `[PROJECT]`, `[ROOM.Rn]`, números com ponto
decimal (en‑US), comprimentos em metros, contorno como `PointN=x y`. O gerador grava em Latin‑1 com CRLF.

## Verificado no DIALux evo 14 (importação de `examples/duas-salas.json`)

| Chave | Resultado |
|---|---|
| `Name` (projeto e ambiente) | ok: árvore mostra "Exemplo 2 salas › STF Building › STF Storey › Sala A/B" |
| `PointN` | ok (geometria importada) |
| `WorkingPlane` | ok: 0.75 / 0.80 lidos em `WorkplaneHeightDoubleBox` |
| `MF` | ok: 0.67 lido em `MaintenanceFactor`; sem `MF` → 0.80 (padrão) |
| `Height` | **não por ambiente**: o evo cria um único "STF Storey" e as duas salas ficaram com 3.000 m (o maior valor). A Sala A (2.8) precisa ser corrigida pela UI depois da importação. |
| `R_Ceiling`, `R_Floor`, `R_WallN` (%) | **não verificado**: o painel "Alterar graus de reflexão" guarda os últimos valores digitados para todos os ambientes, então não serve de leitura. Conferir no relatório PDF. |
