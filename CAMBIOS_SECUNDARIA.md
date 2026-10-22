# CGAME – adaptación a 3.er año de secundaria (Programación)

## Archivos modificados
| Archivo | Motivo |
|---|---|
| `shared/levels.json` | Contenidos nuevos. Mismos IDs (G1-L1…G3-L3) y 3 niveles por juego. Los niveles de G1 y G3 incluyen un campo `lab` (laboratorio interactivo) y `optimal`. |
| `client/src/index.template.html` | Mecánicas nuevas: preguntas de opción múltiple (G2) y 5 laboratorios interactivos (G1 y G3). Reutilizan HUD, pistas, puntaje, cronómetro y guardado de intentos. |
| `client/cgame.html` | Build regenerado con `python tools/build_client.py`. |
| `backend/recommender/levels.py` | Lee `optimal` / `questions` de los niveles nuevos. **Requiere redeploy.** |
| `backend/tests/test_recommender.py` | Valores óptimos actualizados. |

Sin cambios: endpoints, base de datos, autenticación, fórmula de puntaje, recomendador SVM propio de CGAME y `svm_model.json`.

## Juegos y mecánicas
- **G1 Programadores de Jujuy** (laboratorio + 2/3/4 preguntas)
  - L1 *Riego de la huerta*: constructor de algoritmos con bloques (Avanzar, Regar, Repetir). Los bloques disponibles obligan a usar un ciclo.
  - L2 *Riego inteligente*: suma el bloque condicional «Si el cantero está seco»; el tanque alcanza justo, así que regar todo falla por desperdiciar agua.
  - L3 *Compara y justifica*: se prueban dos algoritmos en la simulación (instrucciones, acciones, agua) y se justifica cuál es más eficiente. Incluye una pregunta de semáforo (condicional).
- **G2 Detective de Código Python** (sin cambios, preguntas).
- **G3 Desafío de Inteligencia Artificial**
  - L1 *Exploradores de datos*: clasificar ejemplos de residuos escolares, con un dato incompleto.
  - L2 *Entrenamiento y evaluación*: regla con variable, comparador y umbral; muestra matriz de confusión (VP, FP, FN, VN) en entrenamiento y prueba. Hay que lograr 85 % en PRUEBA.
  - L3 *SVM*: SVM lineal que se entrena de verdad en el navegador (descenso por subgradiente sobre la pérdida hinge, JavaScript propio, sin dependencias). Se puede cambiar C, quitar la temperatura, evaluar en datos de prueba y tocar el gráfico para predecir puntos nuevos.

Nota sobre el SVM de G3-L3: es una implementación simple y propia en JavaScript (no scikit-learn). Es adecuada para explicar frontera y margen con pocos datos, no para uso productivo.

## Probar localmente
`python tools/build_client.py` y abrir `client/cgame.html` (modo local, sin API). Con servidor: `cgame.html?api=URL`.
Tests backend: `cd backend && python -m unittest discover -s tests`.

## Publicar sin cortar el servicio
1. Subir el backend (`levels.py` + `shared/levels.json`) a PythonAnywhere y recargar la web app. Hasta entonces el servidor viejo sigue aceptando los intentos, porque los IDs no cambiaron, pero calcula la eficiencia con los óptimos antiguos.
2. Subir `client/cgame.html` (renombrado como el `index.html` publicado actual).
