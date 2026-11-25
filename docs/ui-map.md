# Mapa da UI do DIALux evo 14 (UI Automation)

DIALux evo 14.0 (instalado como 5.14.0.5), interface em português. Aplicação WPF: quase todos os
controles têm AutomationId estável. Dumps completos em `docs/ui-dumps/`.

Observações gerais:
- Use `walk()` (varredura por `children()`). O `descendants()` do pywinauto deixa de fora nós
  como as abas de modo.
- Os campos de texto WPF só confirmam o valor quando perdem o foco: depois de `SetValue`, mova o
  foco por UIA (`set_focus()` em outro controle).
- A vista 3D/planta (`_renderView` › `WindowsFormsHost`) é opaca à UIA. Nada do fluxo depende dela.
- Diálogos de arquivo são o diálogo padrão do Windows (`cls=#32770`, filho da janela principal):
  `1148` = Edit "Nome:", `1` = Abrir, `2` = Cancelar.

## Janela principal
| Elemento | Identificação |
|---|---|
| Janela | `aid=MainWindow`; título `"<caminho>.evo[*] - DIALux evo 14.0  (64-Bit)"` (`*` = não salvo) |
| Menu | `MainMenu` › `File` (`New`, `OpenProject`, `CloseProject`, `Save`, `SaveAs`, `Import`, `Settings`, `CloseApplication`) |
| Submenu Importar | `ImportDrawing`, `ImportIfc`, `ImportStf`, `ImportDlx4`, `ImportLuminaire`, `ImportDaylightsystem`, `ImportFurniture`, `ImportProjectImage`, `ImportLayout` |
| Barra de comandos | `Save`, `Undo`, `Redo` |
| Login | `LoginBadge`; sem login aparece `LoginModeControlLogin` (`TextBoxEmail`, `PART_PasswordBox`, `LoginButton`) |
| Modos (TabItem, `name` = classe) | `Dial.Dialux.InteractionModes.ProjectInfoMode`, `.BuildingConstructionMode`, `.LightingDesignMode`, `.Results.ResultMode`, `.ExportMode`, `.Output.OutputMode`, `.PluginSelectionMode` |
| Cálculo | `CalculationButtons` › `CalculationButtonStart`, `CommonCalculationButton`, `DiscardResultsButton`, `CalculationButtonShowCalcOptionsDropDown` |
| Aviso de licença | `ProVersionAdvertisingWindow` (`TextBlockAdvertisingTitle`, `ButtonClose`) |

## Tela inicial (`StartModeControl`)
`StartNewProject`, `StartImportPlan`, `StartImportIfc`, `StartRoomPlanning`, `StartStreet`,
`LoadProjectButton`, itens recentes `LoadProject`.

## Importação STF
`File` › `Import` › `ImportStf` → diálogo "Carregar ficheiro STF" → o projeto abre direto em Construção.
Título passa a `<pasta do .stf>\<nome>.evo` (ainda não salvo).

## Construção (`_toolTabControl`, abas por `aid`)
`DrawingTool`, `IfcTool`, `SiteTool`, `StoreyTool`, `BuildingOpeningTool`, `FacadeElementTool`,
`SpaceTool`, `RoomElementTool`, `RoofTool`, `CeilingTool`, `OpeningTool`, `FurnitureTool`,
`MaterialTool`, `LinesAndTextTool`, `MultiSelectionTool`, `ViewTool`, `ProjectTreeTool`.

- **Árvore** (`ProjectTreeTool`): itens `ListItem` com `aid` = caminho, p.ex.
  `Exemplo 2 salas_STF Building_STF Storey_Salas e espaços_Sala A`. Selecionar = SelectionItem.
- **Ambiente** (`SpaceTool`, com o ambiente selecionado): `ObjectName`, `ObjectDescription`, `Height`,
  `WorkplaneNameTextBox`, `WorkplaneHeightDoubleBox`, `WorkplaneMarginDoubleBox`,
  `MaintenanceStandardComboBox`, `MaintenanceFactor`.
- **Refletâncias** (`MaterialTool` › `aid_ChangedSpaceSurfaceRho`): `CeilingRho_Value`, `WallRho_Value`,
  `FloorRho_Value` (%), `ApplyRhoButton`. Não serve como leitura do estado do ambiente.

## Luz (`LightingDesignMode`)
Abas: `LuminaireArrangementTool`, `LampTool`, `JointTool`, `FilterTool`, `LightSceneTool`, `SpaceTool`,
`MaintenanceFactorTool`, `EnergyPerformanceTool`, `EmergencyLightingLuminaireArrangementTool`, ...

`LuminaireArrangementTool`: `aid_DrawRectangle`, `aid_DrawPolygon`, `aid_DrawCircle`, `aid_DrawLine`,
`aid_DrawPoint`, **`aid_ArrangementFromSpace`** (distribuição automática para áreas),
`aid_StartChangePrototypeSelected`, `aid_StartChangePrototypeAll`; grupo `ToolPartLuminaireType`
(luminária ativa).

## Ainda não mapeado (bloqueado pela licença, ver README)
Parâmetros do arranjo automático, cálculo/progresso, Documentação (`OutputMode`) e exportação de PDF.
