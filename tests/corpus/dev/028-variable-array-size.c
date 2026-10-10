#include <stdio.h>

int main(void) {
    int n = 5;
    int marks[n];
    int i;
    int total = 0;
    for (i = 0; i < n; i++) {
        marks[i] = 50 + i * 7;
        total += marks[i];
    }
    printf("total of %d marks = %d\n", n, total);
    return 0;
}
