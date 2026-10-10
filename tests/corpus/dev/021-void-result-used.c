#include <stdio.h>

void print_header(void) {
    printf("=== Report ===\n");
}

int main(void) {
    int r = print_header();
    printf("header printed, r = %d\n", r);
    return 0;
}
