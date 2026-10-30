# Estado de los modelos al entregar WAKI IA 4.1

| Capacidad | Elección | Evidencia | Estado |
|---|---|---|---|
| Agua / cauce | SegFormer-B0 ADE20K original (perfil `clasico`) | 43.25% de píxeles marcados en la foto de residuos del demo v2.1 | Demostración visual; no precisión validada en esa foto |
| Agua turbia / cauce | SegFormer-B0 fine-tuned (perfil `chillon`) | IoU global 86.18% en 4 fotografías de test independientes | Piloto evaluado; limitado por el tamaño del test |
| Objetos específicos | Grounding DINO Tiny | Amplia variedad de candidatos en la foto de demo; mF1 exploratorio 19.67% en prueba de 5 fotos de acumulaciones | Experimental; no confiable para diagnosticar materiales |
| Objetos multiescala | YOLOE-26s-seg | Cajas más localizadas en algunos objetos, duplicados y omisiones | Experimental; falta benchmark cuantitativo |
| Detección supervisada local | YOLO26n entrenado | mAP@50 0.45% en 4 imágenes de validación | EXCLUIDO de la integración final |

La combinación de detectores no está validada para mejorar precisión. Su valor actual es añadir *zonas para revisión humana* sin ocultar las fuentes ni los conflictos de etiqueta.
