/**
 * Copyright 2026 esh contributors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 **/

#include "shell.h"

static int hello(int argc, char **argv) {
  (void)argc;
  (void)argv;
  printf("Hello from 80C51!\n");
  return 0;
}

static int sum(int argc, char **argv) {
  int total = 0;

  for (int i = 1; i < argc; i++) {
    total += atoi(argv[i]);
  }

  printf("%d\n", total);
  return 0;
}

ADD_CMD(hello, "Print a greeting", hello);
ADD_CMD(sum, "Add up to 5 integers: sum 1 2 3", sum);

int main(void) {
  prompt();
  return 0;
}
