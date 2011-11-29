#ifndef _STATS_FILE_H_
#define _STATS_FILE_H_
#include <stdio.h>

struct stats_file {
  char *sf_path;
  FILE *sf_file;
  char *sf_mark;
  unsigned int sf_empty:1;
};

int stats_file_open(struct stats_file *sf, const char *path);
int stats_file_mark(struct stats_file *sf, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
int stats_file_close(struct stats_file *sf);

#endif
