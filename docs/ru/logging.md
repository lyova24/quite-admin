# Логирование

quite-admin использует настройки логирования приложения. Библиотека не вызывает
`basicConfig()`, `dictConfig()` или `structlog.configure()`, не задаёт уровни, не добавляет
console/file handlers и не перенастраивает логгеры приложения/root. По умолчанию используется
`logging.getLogger("quite_admin")` с `NullHandler` и включённым propagation.

## Выбор логгера

```python
import logging
from quite_admin import Admin

admin = Admin(
    auth=auth_backend,
    secret_key=session_secret,
    logger=logging.getLogger("quite_admin"),  # Необязательно: это значение по умолчанию
)
```

Можно передать stdlib logger, `LoggerAdapter`, picologging или структурированный логгер.
`LoggerProtocol` описывает методы `debug`, `info`, `warning`; они могут возвращать
`None` либо awaitable. Выбранный логгер также доступен как `admin.logger`.

| Режим | Форма вызова | Где находятся поля |
| --- | --- | --- |
| `log_structured=False` (по умолчанию) | `logger.info(event, extra={"quite_admin": fields})` | `LogRecord.quite_admin` в stdlib logging; ограничение picologging описано ниже |
| `log_structured=True` | `logger.info(event, **fields)` | В полях структурированного события |

Для структурированного режима нужно явно передать логгер. Stdlib `Logger` и
`LoggerAdapter` с `log_structured=True` отклоняются при инициализации.
Контекст `LoggerAdapter` сохраняется вместе с namespace `quite_admin`, в том числе
на версиях Python, где адаптер по умолчанию отбрасывает переданный в вызове `extra`.

## FastAPI и Uvicorn

FastAPI использует Python logging, а серверные, access-логи и ошибки настраиваются
в [Uvicorn](https://uvicorn.dev/concepts/logging/). Чтобы отправить события библиотеки
в обычный formatter Uvicorn и сохранить его существующие логгеры:

```python
from copy import deepcopy
import uvicorn
from uvicorn.config import LOGGING_CONFIG

log_config = deepcopy(LOGGING_CONFIG)
log_config["loggers"]["quite_admin"] = {
    "handlers": ["default"],
    "level": "INFO",
    "propagate": False,
}

if __name__ == "__main__":
    uvicorn.run("myapp:app", log_config=log_config)
```

Обычный текстовый formatter показывает имя события. Для JSON с метаданными используйте
свой formatter или `structlog.stdlib.ProcessorFormatter` с `structlog.stdlib.ExtraAdder`,
который добавит `LogRecord.quite_admin` в структурированный вывод.
Не направляйте события библиотеки в `uvicorn.access`: его formatter требует поля access-record Uvicorn.
Вместо Python-конфигурации можно передать Uvicorn параметр `--log-config`.

## Litestar LoggingConfig и очереди

Актуальный стабильный Litestar 2 предоставляет `LoggingConfig`, queue-based handler,
picologging и `StructlogPlugin`; см. [документацию Litestar](https://docs.litestar.dev/2/usage/logging.html).
Передавайте логгер приложения, чтобы админка использовала тот же backend:

```python
from litestar import Litestar
from litestar.logging import LoggingConfig
from litestar.middleware.logging import LoggingMiddlewareConfig
from quite_admin import Admin

app = Litestar(
    logging_config=LoggingConfig(logging_module="logging", log_exceptions="always"),
    middleware=[LoggingMiddlewareConfig(
        request_log_fields=("method", "path"),
        response_log_fields=("status_code",),
    ).middleware],
)
admin = Admin(
    auth=auth_backend,
    secret_key=session_secret,
    logger=app.get_logger("quite_admin"),
)
admin.mount_litestar(app)
```

Queue listener, formatter и уровни остаются под управлением приложения.
Для picologging задайте `logging_module="picologging"` и так же передайте `app.get_logger(...)`.
Если явно не выбрать модуль, Litestar 2 использует picologging, когда он установлен.
Обычный `logging.getLogger()` не возвращает picologging logger.

Проверенный picologging 0.9.3 принимает, но игнорирует `extra`: имена событий и уровни
работают, однако `LogRecord.quite_admin` недоступен. Не используйте `%(quite_admin)s` в его formatter.
Если нужны метаданные, выберите `logging_module="logging"`, как в примере выше, либо `StructlogPlugin`.
quite-admin не изменяет picologging и фильтры приложения ради обхода этого ограничения backend.

## StructlogPlugin и структурированные события

Установите `structlog` в приложение и используйте плагин Litestar:

```python
from litestar import Litestar
from litestar.middleware.logging import LoggingMiddlewareConfig
from litestar.plugins.structlog import StructlogConfig, StructlogPlugin
from quite_admin import Admin

plugin = StructlogPlugin(StructlogConfig(
    middleware_logging_config=LoggingMiddlewareConfig(
        request_log_fields=("method", "path"),
        response_log_fields=("status_code",),
    ),
))
app = Litestar(plugins=[plugin])
admin = Admin(
    auth=auth_backend,
    secret_key=session_secret,
    logger=app.get_logger("quite_admin").bind(component="admin"),
    log_structured=True,
)
admin.mount_litestar(app)
```

В FastAPI после настройки structlog в приложении передайте `structlog.get_logger("quite_admin")`
с `log_structured=True`. Поддерживается и логгер с настроенным
`structlog.stdlib.ProcessorFormatter`; конфигурация renderer остаётся за приложением.

Добавьте `structlog.contextvars.merge_contextvars` в цепочку processors для request ID
и tracing context. Админка не привязывает и не очищает контекст приложения.
ASGI-граница сохраняет контекст запроса, а AnyIO переносит его в worker threads
синхронных context callbacks собственных страниц.

Loguru использует ту же форму вызова со структурированными полями:

```python
from loguru import logger

admin = Admin(
    auth=auth_backend,
    secret_key=session_secret,
    logger=logger.bind(component="admin"),
    log_structured=True,
)
```

Поля доступны в `record["extra"]` Loguru. Sinks и очереди настраивает приложение.
structlog, Loguru и picologging не становятся обязательными зависимостями quite-admin.

## Middleware логирования запросов

Монтирование совместимо с чтением тела в `LoggingMiddleware` Litestar: поддержаны
кешированное тело, потоковые формы и лимит админки в 1 MiB.
Наш ASGI-handler локально предоставляет метод получения лимита для Litestar 2
и переводит публичный `Request.stream()` в ASGI receive-сообщения. Отдельный receive guard
этого mount считает байты до middleware, в том числе при повторных попытках чтения парсером.
Классы фреймворка глобально не изменяются.

По умолчанию middleware Litestar логирует тела и cookies. Для админки используйте
ограниченный набор полей из примеров выше: login-body содержит пароль и CSRF,
ответы — session cookies и значения записей. Админка не может удалить данные,
которые внешнее middleware приложения самостоятельно записывает в логи.

## События библиотеки

| Событие | Уровень | Поля |
| --- | --- | --- |
| `quite_admin.login_succeeded` | INFO | `status_code` |
| `quite_admin.login_failed` | WARNING | `status_code` |
| `quite_admin.login_throttled` | WARNING | `status_code` |
| `quite_admin.logout` | INFO | `status_code` |
| `quite_admin.record_created` | INFO | `collection`, `status_code` |
| `quite_admin.record_updated` | INFO | `collection`, `status_code` |
| `quite_admin.record_deleted` | INFO | `collection`, `status_code` |
| `quite_admin.record_conflict` | WARNING | `collection`, `status_code` |
| `quite_admin.validation_failed` | DEBUG | `collection`, `status_code` |
| `quite_admin.permission_denied` | WARNING | `collection`, `operation`, `status_code` |
| `quite_admin.csrf_rejected` | WARNING | `status_code` |

Метаданные, которые добавляет библиотека, не содержат credentials, identity, токены, cookies, headers, URL,
query string, ключи записей, значения полей и исходные сообщения исключений.
Дополнительный контекст, привязанный приложением к логгеру, остаётся под вашим управлением.
События изменения данных записываются после успешного commit адаптера.
Это диагностические события, а не надёжное хранилище audit log.

Админка не добавляет собственный access-log на каждый запрос и не перехватывает
неожиданные исключения ради повторного логирования: они доходят до error pipeline
приложения/сервера. Если sink или processor падает, библиотека пытается записать
`quite_admin.logging_failed` через stdlib logger только с `event_name` и `error_type`.
Сбой logging sink не меняет HTTP-результат и не откатывает уже сохранённую запись.

## Проверяемая совместимость

Тесты покрывают formatter Uvicorn, `LoggingConfig` и настоящий queue listener Litestar,
`LoggerAdapter`, JSON через `StructlogPlugin`, Loguru, перенос контекста, body-reading
middleware, исключение чувствительных данных и отказ sink.
Опциональный picologging проверяется отдельным CI job на Python 3.12 через
`uv sync --locked --group logging-check`. Основная матрица Python 3.11–3.15 не требует
picologging и не гарантирует поддержку его C-расширения для каждой комбинации Python и ОС.
