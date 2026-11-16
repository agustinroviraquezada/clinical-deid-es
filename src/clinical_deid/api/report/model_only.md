# Model-only evaluation (MEDDOCAN)

Entity-level, strict span + type, micro-averaged; spans on BIO tokens.
Model: run 1 fine-tuned from `BSC-LT/roberta-base-biomedical-clinical-es` (revision `af1b189bbc1303f23f64661a4a913c4da302d821`).
AC-02 target on test: recall >= 0.90 and precision >= 0.85.

## dev

### Overall

| Name | Recall | Precision | F1 | Support |
| --- | --- | --- | --- | --- |
| overall | 0.975 | 0.970 | 0.972 | 5801 |

### Per category

| Name | Recall | Precision | F1 | Support |
| --- | --- | --- | --- | --- |
| NAME | 0.969 | 0.968 | 0.968 | 1092 |
| DATE | 0.992 | 0.978 | 0.985 | 724 |
| LOCATION | 0.963 | 0.958 | 0.961 | 1982 |
| ID | 0.983 | 0.971 | 0.977 | 745 |
| CONTACT | 0.993 | 0.982 | 0.987 | 272 |
| AGE | 0.985 | 0.988 | 0.987 | 521 |
| PROFESSION | 0.500 | 0.500 | 0.500 | 4 |
| OTHER | 0.983 | 0.985 | 0.984 | 461 |

### Per MEDDOCAN type

| Name | Recall | Precision | F1 | Support |
| --- | --- | --- | --- | --- |
| CALLE | 0.956 | 0.933 | 0.944 | 434 |
| CENTRO_SALUD | 0.500 | 0.500 | 0.500 | 2 |
| CORREO_ELECTRONICO | 0.996 | 1.000 | 0.998 | 241 |
| EDAD_SUJETO_ASISTENCIA | 0.985 | 0.988 | 0.987 | 521 |
| FAMILIARES_SUJETO_ASISTENCIA | 0.717 | 0.759 | 0.737 | 92 |
| FECHAS | 0.992 | 0.978 | 0.985 | 724 |
| HOSPITAL | 0.907 | 0.927 | 0.917 | 140 |
| ID_ASEGURAMIENTO | 0.985 | 1.000 | 0.992 | 194 |
| ID_CONTACTO_ASISTENCIAL | 1.000 | 0.970 | 0.985 | 32 |
| ID_EMPLEO_PERSONAL_SANITARIO | 0.000 | 0.000 | 0.000 | 1 |
| ID_SUJETO_ASISTENCIA | 0.973 | 0.944 | 0.958 | 292 |
| ID_TITULACION_PERSONAL_SANITARIO | 0.996 | 0.983 | 0.989 | 226 |
| INSTITUCION | 0.750 | 0.692 | 0.720 | 72 |
| NOMBRE_PERSONAL_SANITARIO | 0.986 | 0.976 | 0.981 | 497 |
| NOMBRE_SUJETO_ASISTENCIA | 0.998 | 0.996 | 0.997 | 503 |
| NUMERO_FAX | 0.833 | 0.625 | 0.714 | 6 |
| NUMERO_TELEFONO | 1.000 | 0.926 | 0.962 | 25 |
| OTROS_SUJETO_ASISTENCIA | 0.000 | 0.000 | 0.000 | 6 |
| PAIS | 0.991 | 0.991 | 0.991 | 347 |
| PROFESION | 0.500 | 0.500 | 0.500 | 4 |
| SEXO_SUJETO_ASISTENCIA | 0.996 | 0.985 | 0.990 | 455 |
| TERRITORIO | 0.981 | 0.984 | 0.982 | 987 |

## test

### Overall

| Name | Recall | Precision | F1 | Support |
| --- | --- | --- | --- | --- |
| overall | 0.974 | 0.965 | 0.969 | 5661 |

### Per category

| Name | Recall | Precision | F1 | Support |
| --- | --- | --- | --- | --- |
| NAME | 0.986 | 0.970 | 0.978 | 1084 |
| DATE | 0.993 | 0.984 | 0.989 | 611 |
| LOCATION | 0.948 | 0.941 | 0.945 | 1935 |
| ID | 0.993 | 0.978 | 0.986 | 754 |
| CONTACT | 0.979 | 0.968 | 0.974 | 282 |
| AGE | 0.994 | 0.987 | 0.990 | 518 |
| PROFESSION | 0.889 | 0.533 | 0.667 | 9 |
| OTHER | 0.976 | 0.989 | 0.983 | 468 |

### Per MEDDOCAN type

| Name | Recall | Precision | F1 | Support |
| --- | --- | --- | --- | --- |
| CALLE | 0.956 | 0.929 | 0.943 | 413 |
| CENTRO_SALUD | 0.333 | 0.400 | 0.364 | 6 |
| CORREO_ELECTRONICO | 0.992 | 0.992 | 0.992 | 249 |
| EDAD_SUJETO_ASISTENCIA | 0.994 | 0.987 | 0.990 | 518 |
| FAMILIARES_SUJETO_ASISTENCIA | 0.827 | 0.691 | 0.753 | 81 |
| FECHAS | 0.993 | 0.984 | 0.989 | 611 |
| HOSPITAL | 0.885 | 0.943 | 0.913 | 130 |
| ID_ASEGURAMIENTO | 0.995 | 1.000 | 0.997 | 198 |
| ID_CONTACTO_ASISTENCIAL | 0.974 | 0.950 | 0.962 | 39 |
| ID_EMPLEO_PERSONAL_SANITARIO | 0.000 | 0.000 | 0.000 | 0 |
| ID_SUJETO_ASISTENCIA | 0.989 | 0.956 | 0.972 | 283 |
| ID_TITULACION_PERSONAL_SANITARIO | 1.000 | 0.992 | 0.996 | 234 |
| INSTITUCION | 0.507 | 0.459 | 0.482 | 67 |
| NOMBRE_PERSONAL_SANITARIO | 0.998 | 0.996 | 0.997 | 501 |
| NOMBRE_SUJETO_ASISTENCIA | 1.000 | 0.998 | 0.999 | 502 |
| NUMERO_FAX | 0.857 | 0.667 | 0.750 | 7 |
| NUMERO_TELEFONO | 0.885 | 0.852 | 0.868 | 26 |
| OTROS_SUJETO_ASISTENCIA | 0.000 | 0.000 | 0.000 | 7 |
| PAIS | 0.981 | 0.973 | 0.977 | 363 |
| PROFESION | 0.889 | 0.533 | 0.667 | 9 |
| SEXO_SUJETO_ASISTENCIA | 0.991 | 0.989 | 0.990 | 461 |
| TERRITORIO | 0.975 | 0.975 | 0.975 | 956 |

Data: MEDDOCAN corpus (Marimon et al., 2019), licensed CC BY 4.0. MEDDOCAN contains clinical case reports with synthetic personal data; performance on real notes will likely be lower.
