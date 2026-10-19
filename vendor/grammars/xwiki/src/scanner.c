#include "tree_sitter/alloc.h"
#include "tree_sitter/array.h"
#include "tree_sitter/parser.h"
#include <assert.h>
#include <ctype.h>
#include <stdio.h>
#include <string.h>

typedef enum {
  LINE_ENDING,
  PARAGRAPH_START,
  PARAGRAPH_END,
  ERROR,
} TokenType;

// The scanner changes what it scans based on these states.
typedef enum {
  UNDEFINED_STATE,
  BEGINNING_OF_LINE,
  INLINE,
  // Block states
  TABLE_CONTEXT,
  HEADER_CONTEXT,
  // Special states
  VERBATIM_CONTEXT,
  MACRO_CONTEXT,
} ScannerState;

// The stateful scanner.
typedef struct {
  // The preceeding special state.
  ScannerState preceeding_special_state;
  // The stack of scanner states.
  Array(ScannerState) * state_stack;
} Scanner;

// Return an explicit error symbol.
static bool error(TSLexer *lexer) {
  lexer->result_symbol = ERROR;
  return true;
}

static bool scan(Scanner *payload, TSLexer *lexer, const bool *valid_symbols) {
  return false;
}

// Serializes the scanner into the provided buffer.
#define COPY_TO_BYTE_BUFFER(EXPR)                                              \
  memcpy(&buffer[size], (void *)(EXPR), sizeof(EXPR));                         \
  size += sizeof(EXPR);
static unsigned serialize(Scanner *s, char *buffer) {
  unsigned size = 0;

  COPY_TO_BYTE_BUFFER(&s->preceeding_special_state);
  COPY_TO_BYTE_BUFFER(&s->state_stack->size);
  for (long i = 0; i < s->state_stack->size; i++) {
    ScannerState *state = array_get(s->state_stack, i);
    COPY_TO_BYTE_BUFFER(state);
  }

  return size;
}

// De-serializes the scanner from the provided buffer.
#define COPY_FROM_BYTE_BUFFER(EXPR)                                            \
  memcpy((void *)EXPR, &buffer[size], sizeof(EXPR));                           \
  size += sizeof(EXPR);
static void deserialize(Scanner *s, const char *buffer, unsigned length) {
  size_t size = 0;
  COPY_FROM_BYTE_BUFFER(s->preceeding_special_state);

  uint32_t array_size;
  COPY_FROM_BYTE_BUFFER(&array_size);
  s->state_stack = ts_calloc(1, sizeof(Array(ScannerState)));

  for (uint32_t i = 0; i < array_size; i++) {
    ScannerState state;
    COPY_FROM_BYTE_BUFFER(&state);
    array_push(s->state_stack, state);
  }
}

//============================ Treesitter API ==================================

void *tree_sitter_my_language_external_scanner_create() {
  Scanner *s = (Scanner *)ts_malloc(sizeof(Scanner));
  s->preceeding_special_state = UNDEFINED_STATE;
  s->state_stack = ts_calloc(1, sizeof(Array(ScannerState)));
  return s;
}

void tree_sitter_my_language_external_scanner_destroy(void *payload) {
  Scanner *s = (Scanner *)payload;
  array_delete(s->state_stack);
  ts_free(s);
}

bool tree_sitter_my_language_external_scanner_scan(void *payload,
                                                   TSLexer *lexer,
                                                   const bool *valid_symbols) {
  Scanner *s = (Scanner *)payload;
  return scan(s, lexer, valid_symbols);
}

unsigned tree_sitter_my_language_external_scanner_serialize(void *payload,
                                                            char *buffer) {
  Scanner *s = (Scanner *)payload;
  return serialize(s, buffer);
}

void tree_sitter_my_language_external_scanner_deserialize(void *payload,
                                                          const char *buffer,
                                                          unsigned length) {
  Scanner *s = (Scanner *)payload;
  deserialize(s, buffer, length);
}
