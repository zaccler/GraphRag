# CODE_MAP

Project navigation map: where endpoints, functions, classes, and main constants are declared.

## Fast Search

```powershell
rg -n "symbol_name"
rg -n "def function_name|class ClassName"
rg -n "@app\.|/parse/packages|/ask" server.py browser_extension
```

## Main Flows

- Ask flow: `browser_extension/popup.js` -> `POST /ask` or `/ask_debug` -> `lms/answer_service.py` -> Dgraph context -> LLM -> response.
- Package parse flow: MGR -> `POST /parse/packages` -> `xdt/scp/parser.py` -> `raw/lit/packages` -> `knb/ragu_runtime.py` -> Dgraph.
- Docs parse flow: MGR -> `POST /parse/docs-registry` or `/parse/url` -> parser/web docs -> Dgraph.
- Chat history: extension -> `/dhb/log-chat` and `/dhb/chat-history` -> `dhb/chat_logs.py` -> Google Sheet or local jsonl.
- Auth flow: extension -> `/auth/request-code`, `/auth/verify-code` -> `mgr/auth_service.py` -> SMTP code.

## FastAPI Endpoints

- `server.py:335` `GET /status` -> `status()`
- `server.py:346` `POST /auth/request-code` -> `auth_request_code()`
- `server.py:360` `POST /auth/verify-code` -> `auth_verify_code()`
- `server.py:369` `POST /dhb/log-chat` -> `dhb_log_chat()`
- `server.py:375` `POST /dhb/chat-history` -> `dhb_chat_history()`
- `server.py:386` `POST /ask` -> `ask()`
- `server.py:409` `POST /ask_debug` -> `ask_debug()`
- `server.py:437` `POST /rebuild` -> `rebuild()`
- `server.py:465` `POST /parse/url` -> `parse_url()`
- `server.py:486` `POST /parse/docs-registry` -> `parse_docs_registry()`
- `server.py:510` `POST /parse/packages` -> `parse_packages()`

## `server.py`

Functions:
- `ensure_dirs()` line 63
- `activate_runtime_components()` line 72
- `has_live_index()` line 80
- `record_background_failure()` line 84
- `should_rebuild_after_parse()` line 90
- `index_text_files()` line 100
- `background_rebuild()` line 133
- `background_parse_registry()` line 171
- `background_parse_packages()` line 238
- `async startup()` line 307
- `async status()` line 336
- `async auth_request_code()` line 347
- `async auth_verify_code()` line 361
- `async dhb_log_chat()` line 370
- `async dhb_chat_history()` line 376
- `async ask()` line 387
- `async ask_debug()` line 410
- `async rebuild()` line 438
- `async parse_url()` line 466
- `async parse_docs_registry()` line 487
- `async parse_packages()` line 511

## `api/config.py`

Constants:
- `LLM_API_KEY` line 26
- `EMBEDDING_API_KEY` line 27
- `BASE_URL` line 29
- `EMBEDDING_BASE_URL` line 30
- `LLM_MODEL_NAME` line 32
- `EMBEDDER_MODEL_NAME` line 33
- `TOKENIZER_MODEL` line 34
- `RAW_LIT_DIR` line 36
- `DOCS_REGISTRY_PATH` line 37
- `PACKAGE_REGISTRY_PATH` line 38
- `DOCS_RAW_DIR` line 39
- `PACKAGE_RAW_DIR` line 40
- `DHB_DIR` line 41
- `STORAGE_DIR` line 42
- `INDEX_MANIFEST_PATH` line 43
- `EMBEDDER_DIM` line 45
- `DGRAPH_ADDRESS` line 46
- `DEFAULT_LLM_RETRY_TIMES_SEC` line 49
- `DEFAULT_EMBEDDING_RETRY_TIMES_SEC` line 50
- `LLM_RETRY_TIMES_SEC` line 52
- `EMBEDDING_RETRY_TIMES_SEC` line 53
- `LLM_TIMEOUT_SEC` line 58
- `EMBEDDING_TIMEOUT_SEC` line 59
- `LLM_CONNECT_TIMEOUT_SEC` line 60
- `EMBEDDING_CONNECT_TIMEOUT_SEC` line 61
- `LLM_RATE_MAX_PER_MINUTE` line 62
- `EMBEDDING_RATE_MAX_PER_MINUTE` line 63
- `LLM_RATE_MAX_SIMULTANEOUS` line 64
- `EMBEDDING_RATE_MAX_SIMULTANEOUS` line 65
- `CHUNK_MAX_SIZE` line 66
- `ASK_TIMEOUT_SEC` line 67
- `SEARCH_TOP_K` line 68
- `FAST_CONTEXT_LIMIT` line 69
- `FAST_CONTEXT_CHAR_LIMIT` line 70

Functions:
- `_retry_schedule()` line 11
- `build_timeout()` line 22

## `api/models.py`

Classes:
- `AskRequest` line 4
- `AskResponse` line 8
- `AuthCodeRequest` line 12
- `AuthVerifyRequest` line 16
- `AuthResponse` line 21
- `ChatLogRequest` line 28
- `ChatHistoryRequest` line 34
- `AskDebugResponse` line 39
- `ParseUrlRequest` line 46
- `ParsePackagesRequest` line 51
- `ParseDocsRegistryRequest` line 58
- `StatusResponse` line 65

## `lms/answer_service.py`

Constants:
- `STOP_WORDS` line 11

Functions:
- `_answer_text()` line 18
- `_has_context()` line 30
- `_conversation()` line 41
- `_search_terms()` line 62
- `_row_content()` line 73
- `_fast_context_from_dgraph()` line 88
- `async _answer_from_fast_context()` line 114
- `async answer_with_context()` line 123
- `async answer_with_timeout()` line 153

## `knb/package_downloads.py`

Constants:
- `OVERVIEW_LIMIT` line 9
- `OVERVIEW_EXAMPLES` line 10

Functions:
- `_query_parts()` line 13
- `_is_download_question()` line 21
- `_is_overview_question()` line 26
- `_chunk_texts()` line 47
- `_field()` line 79
- `_download_url()` line 85
- `_package_record()` line 89
- `_package_records()` line 124
- `package_overview_answer()` line 139
- `package_download_answer()` line 172

## `knb/ragu_runtime.py`

Functions:
- `build_llm_client()` line 55
- `build_embedding_client()` line 71
- `build_storage_settings()` line 87
- `build_graph_components()` line 103
- `reset_storage()` line 138
- `list_text_files()` line 144
- `_file_key()` line 157
- `_file_hash()` line 165
- `_file_record()` line 173
- `load_index_manifest()` line 183
- `save_index_manifest()` line 200
- `filter_unindexed_files()` line 206
- `mark_files_indexed()` line 226
- `has_persisted_index()` line 244
- `_load_json_file()` line 274
- `_decode_nano_matrix()` line 280
- `async migrate_local_runtime_storage_to_dgraph()` line 294
- `async build_storage_from_files()` line 348
- `async build_storage_from_folder()` line 368
- `_temp_storage_dir()` line 372
- `_cleanup_storage_dir()` line 378
- `_promote_staged_storage()` line 383
- `_rollback_promoted_storage()` line 393
- `rebuild_transactionally()` line 399
- `rebuild_transactionally_from_files()` line 417

## `knb/dgraph_adapter.py`

Constants:
- `ENTITY_TYPE` line 12
- `RELATION_TYPE` line 13
- `GRPC_MAX_MESSAGE_BYTES` line 14
- `GRPC_OPTIONS` line 15
- `DGRAPH_SCHEMA` line 20

Classes:
- `DgraphStorage` line 159

Functions:
- `_json_dumps()` line 61
- `_json_loads()` line 65
- `_uid_alias()` line 76
- `_entity_to_obj()` line 80
- `_entity_from_row()` line 95
- `_relation_to_obj()` line 107
- `_relation_from_row()` line 129

## `knb/dgraph_unified_storage.py`

Constants:
- `KV_TYPE` line 14
- `EMBEDDING_TYPE` line 15
- `GRPC_MAX_MESSAGE_BYTES` line 16
- `GRPC_OPTIONS` line 17
- `VECTOR_QUERY_PAGE_SIZE` line 21
- `DGRAPH_UNIFIED_SCHEMA` line 23

Classes:
- `_DgraphStoreBase` line 74
- `DgraphKVStorage` line 122
- `DgraphVectorStorage` line 226

Functions:
- `_namespace_name()` line 45
- `_json_dumps()` line 49
- `_json_loads()` line 53
- `_cosine_similarity()` line 62

## `xdt/scp/parser.py`

Constants:
- `PACKAGE_MAX_VERSIONS_DEFAULT` line 25
- `GITHUB_MAX_RELEASES_DEFAULT` line 26
- `REFRESHABLE_SOURCE_TYPES` line 602

Functions:
- `google_sheet_csv_url()` line 29
- `format_google_sheet_text()` line 48
- `parse_google_sheet()` line 73
- `github_repo_from_url()` line 88
- `github_auth_headers()` line 96
- `format_github_release_text()` line 100
- `parse_github_releases()` line 146
- `format_nuget_package_text()` line 169
- `parse_nuget_package()` line 205
- `format_pypi_package_text()` line 227
- `parse_pypi_package()` line 270
- `format_npm_package_text()` line 284
- `parse_npm_package()` line 318
- `parse_maven_coord()` line 331
- `format_maven_package_text()` line 338
- `parse_maven_package()` line 371
- `format_crates_package_text()` line 388
- `parse_crates_package()` line 422
- `docker_repo_parts()` line 433
- `format_docker_image_text()` line 444
- `parse_docker_image()` line 474
- `format_go_module_text()` line 487
- `parse_go_module()` line 516
- `_json_for_text()` line 529
- `sentence_safe_record_text()` line 533
- `package_source_from_line()` line 544
- `load_package_sources()` line 586
- `_text_files()` line 614
- `_has_existing_text()` line 618
- `_copy_changed_text_files()` line 622
- `_parse_source_item()` line 643
- `parse_package_sources()` line 686
- `load_registry()` line 703
- `parse_registry_sources()` line 713

## `xdt/scp/web_docs.py`

Functions:
- `sanitize_filename()` line 13
- `normalize_url()` line 19
- `is_same_docs_scope()` line 26
- `fetch_html()` line 43
- `fetch_json()` line 49
- `fetch_text()` line 55
- `_clean_soup()` line 61
- `_main_container()` line 66
- `_node_text()` line 77
- `_extract_title()` line 83
- `_extract_fragment_block()` line 89
- `extract_page_text()` line 117
- `extract_links()` line 133
- `page_slug()` line 154
- `save_doc()` line 167
- `save_manifest()` line 176
- `crawl_python_docs()` line 185
- `parse_single_doc_page()` line 227

## `xdt/pul/resource_pool.py`

Constants:
- `DEFAULT_CONFIG_PATH` line 14

Classes:
- `ResourceRule` line 18
- `ResourcePool` line 32

Functions:
- `_as_str_dict()` line 47
- `_as_float_tuple()` line 53
- `_load_config()` line 59
- `load_resource_pool()` line 65
- `_headers_for()` line 95
- `get_auth_headers()` line 110
- `request_get()` line 121

## `dhb/chat_logs.py`

Constants:
- `DHB_DIR` line 12
- `CHAT_LOG_PATH` line 13
- `GOOGLE_SHEETS_LOG_WEBHOOK_URL` line 14
- `GOOGLE_SHEETS_LOG_READ_URL` line 15
- `FIELD_ALIASES` line 18

Functions:
- `_append_local()` line 26
- `async _append_google_sheet()` line 32
- `_value()` line 43
- `_normalize_row()` line 52
- `_filter_rows()` line 64
- `_load_local()` line 77
- `_rows_from_json()` line 91
- `_rows_from_csv()` line 102
- `async _load_google_sheet()` line 106
- `async load_chat_history()` line 126
- `async save_chat_log()` line 153

## `dhb/text_db_mirror.py`

Constants:
- `TEXT_DB_SHEET_LOG_PATH` line 10
- `TEXT_DB_SHEET_MAX_TEXT_CHARS` line 11
- `GOOGLE_SHEETS_TEXT_DB_WEBHOOK_URL` line 12

Functions:
- `_clean_cell()` line 15
- `_meta()` line 22
- `_short_path()` line 31
- `_record_from_file()` line 39
- `_save_local()` line 61
- `_send_to_google_sheet()` line 68
- `mirror_text_db_files()` line 81

## `mgr/auth_service.py`

Constants:
- `AUTH_CODE_TTL_SEC` line 12
- `AUTH_CODE_LENGTH` line 13
- `SMTP_HOST` line 14
- `SMTP_PORT` line 15
- `SMTP_USER` line 16
- `SMTP_PASSWORD` line 17
- `SMTP_FROM` line 18
- `SMTP_USE_TLS` line 19
- `SMTP_USE_SSL` line 20
- `EMAIL_RE` line 22
- `AUTH_CODE_ALPHABET` line 23
- `AUTH_CODES` line 24
- `AUTH_CODES_LOCK` line 25

Functions:
- `normalize_email()` line 28
- `generate_auth_code()` line 35
- `smtp_configured()` line 39
- `send_auth_code_email()` line 43
- `store_auth_code()` line 79
- `verify_auth_code()` line 87

## `browser_extension/popup.js`

JS functions/handlers:
- `outputMode()` line 13
- `formatLastResult()` line 17
- `formatDebugOutput()` line 65
- `compactText()` line 87
- `writeOutput()` line 139
- `currentHistoryKey()` line 145
- `currentDraftKey()` line 150
- `saveQuestionDraft()` line 154
- `clearQuestionDraft()` line 160
- `restoreQuestionDraft()` line 165
- `appendTextWithLinks()` line 170
- `setButtonState()` line 199
- `finishButton()` line 215
- `setLoading()` line 220
- `setApiState()` line 228
- `loadSettings()` line 241
- `saveSettings()` line 263
- `loadCodes()` line 269
- `setAuthMode()` line 274
- `saveAuthDraft()` line 288
- `clearAuthDraft()` line 293
- `restoreAuthDraft()` line 298
- `validEmail()` line 309
- `showSentAnimation()` line 313
- `submitRegister()` line 320
- `verifyEmailCode()` line 352
- `loginByCode()` line 385
- `logout()` line 405
- `renderRole()` line 414
- `api()` line 433
- `checkStatus()` line 459
- `refreshStatusBadge()` line 473
- `addMessage()` line 482
- `clearMessages()` line 490
- `historyForCurrentUser()` line 494
- `renderChatHistory()` line 507
- `saveChatLog()` line 521
- `loadServerChatHistory()` line 529
- `logChatToSheet()` line 564
- `openAskDebugModal()` line 578
- `closeAskDebugModal()` line 591
- `runAskDebugFromModal()` line 598
- `ask()` line 636
- `run()` line 663
- `fileRequest()` line 698
- `activateTab()` line 715
- `bindEvents()` line 722

## Quick Explanation Points

- Dgraph stores graph data, chunks, summaries, and vector rows through `knb/dgraph_*`.
- `raw/lit` stores source texts; `dhb/data/indexed_files.json` remembers successfully indexed files.
- LLM is used for normal questions; exact package+version download and package overview can be answered directly from Dgraph.
- Google Sheets is used for chat history and text mirror, not as the main registry source.
