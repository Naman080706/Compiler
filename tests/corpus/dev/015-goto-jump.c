#include <stdio.h>

int main(void) {
    const int LIMIT = 5;
    int i;
    int row;
    for (row = 1; row <= LIMIT; row++) {
        for (i = 1; i <= LIMIT; i++) {
            printf("%d ", row * i);
        }
        printf("\n");
    }
    return 0;
}
