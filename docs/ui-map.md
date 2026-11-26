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

## Contexto de ambiente (essencial)
A barra da vista tem `ToggleButton_RoomContextSelectionButton` › `_menuItemControl` (ExpandCollapse) com itens
`MenuItem_ToggleButton_RoomContextSelectionButton_<n>` (um por ambiente; o nome está no `Text` filho).
**A distribuição automática (`aid_ArrangementFromSpace`) e o painel de refletâncias do ambiente agem sobre o
ambiente de contexto, não sobre a seleção da árvore.** Os itens não expõem estado "marcado"; o arranjo recém-criado
assume como altura de montagem o pé-direito do ambiente de contexto, e é assim que a ferramenta confere.

## Seleção e abas de ferramenta
- O menu Goto (e trocar de modo) **descarta a seleção** atual. Dentro do modo, selecione a aba da ferramenta
  diretamente (SelectionItem), o que mantém o ambiente selecionado.
- O WPF só monta o conteúdo do painel quando a seleção da aba muda: se a aba já está selecionada e vazia,
  selecione a aba da árvore (`ProjectTreeTool`) e volte.

## Documentação (`View` › `ShowOutputMode`)
- `aid_RenderProjectDocument` ("Exibir toda a documentação") gera o documento completo; o total aparece em
  `buttonPageGoTo` ("Página 1 de N"). A lista `FilterTreeListBox` só muda a pré-visualização.
- Exportar: `MenuSaveAs` › `MenuItem` › `ExportFormatMenuItem_Pdf` (também `_Word2007`, `_Ppt2007`, `_Excel2007`)
  → janela "Ficheiro Adobe PDF - Configuração de exportação" (`checkBoxOpenAfterExport`, `buttonOk`) → diálogo
  Salvar do Windows (`1001` = nome, `1` = Salvar). **O diálogo Salvar ignora ValuePattern e `WM_SETTEXT`**
  (grava com o nome padrão na última pasta). Funciona limpar com `WM_SETTEXT` e enviar o caminho como
  `WM_CHAR` direto ao controle, sem foco nem teclado físico. O mesmo método é usado no diálogo Abrir.

## Cálculo
`CalculationButtonStart`; terminou quando `DiscardResultsButton` fica habilitado (7 a 15 s nos testes). Falha
aparece só como mensagem "Ocorreu um erro no cálculo" (`ToggleButtonShowUserLogPopup` › `_listBox`), sem log em
disco. Causa encontrada: LDT com `Isym=1`.

## Modais `InformationBox`
| Texto | Resposta do servidor |
|---|---|
| "Guardar alterações em …?" (ao importar/abrir/novo com projeto alterado) | Não |
| "O projecto não foi guardado desde N Minutos. Guardar agora?" | Não |
| "Os resultados tornam-se inválidos. Continuar?" (alterar após calcular) | Sim, só em ferramentas que alteram o projeto |

## Catálogo de luminárias (`MenuGotoShowLuminaireCatalogPopup`)
`LuminairePopupControl`; itens `<nome> (<código>)_LuminaireCatalogItem`, ordenados pelo uso mais recente.
`ProjectLuminaireFilterToggleButton`: estado 1 lista recentes/importadas, 0 só as já colocadas no projeto. Selecionar
um item define a luminária ativa; o popup não fecha por UIA (não atrapalha).

## Desempenho
`Desktop().windows()` leva cerca de 1 s. O handle da janela principal fica em cache, e as buscas usam o `FindAll`
nativo da UIA com condições de propriedade (visão completa). As abas de modo não aparecem no `FindAll`; use o Goto.

## Achados da sessão com DIALux Pro (teste de 30 dias)
- Com o Pro, `ImportLuminaire` aceita o LDT genérico. A luminária aparece no catálogo como `<nome> (<código>)_LuminaireCatalogItem` (aberto por `MenuGotoShowLuminaireCatalogPopup`).
- Menu **Goto** (`MenuGotoConstructionMode`): `MenuGotoShowProjectTreeTool`, `MenuGotoShowSpaceTool`, `MenuGotoShowLuminaireArrangementTool`, `MenuGotoShowLuminaireCatalogPopup`, `MenuGotoShowCalculationObjectTool`, `MenuGotoShowOutputTreeTool`, `MenuGotoShowMaterialTool`, ... As abas de modo (`Dial.Dialux.InteractionModes.*`) nem sempre aparecem na árvore UIA; o Goto é mais estável.
- `aid_ArrangementFromSpace` cria na hora um arranjo de campo no ambiente selecionado. Painel: `ElementCountX/Y`, `TargetIlluminance` + `ResetFieldToPlanningTarget` (300 lx → 2×2, estimativa de 314 lx), `MountingHeight_Value`, `LightPointHeight_Value`, `GlobalSpaceComboBox`, `NumberOfCurrentLuminairesObjectsTextBlock`, `TotalLuminaireFlux_1`, `Load_1`.
- Modais `InformationBox` (Edit com o texto, botões `Yes`/`No`/`Cancel`): "Guardar alterações em ...?" ao importar com projeto aberto, e o lembrete de autosave "não foi guardado desde 5 minutos". Resposta sempre `No`.
- Cálculo: `CalculationButtonStart` dispara; o popup de opções mostra "Cálculo a funcionar...". **Nos dois testes (2 salas e 1 sala, LDT genérico) terminou com "Ocorreu um erro no cálculo"** (lista de mensagens: `ToggleButtonShowUserLogPopup` › `_listBox`). O DIALux não grava log em disco. Causa ainda não isolada; o próximo teste é com luminária de membro (Philips WT210C).
- Problema em aberto: depois de importar um novo STF, o painel da aba de luminárias pode ficar vazio (só `hideToolsButton`); invocar esse botão não restaurou o conteúdo.
- Nomes da árvore: STF com 1 sala → "Edifício <sala> › Andar <sala>"; com várias → "STF Building › STF Storey". Localizar o ambiente por `_Salas e espaços_<nome>`.
