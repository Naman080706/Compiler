#include <stdio.h>

int main(void) {
    const int limit = 10;
    int i;
    limit = 20;
    for (i = 0; i < limit; i++) {
        printf("%d ", i);
    }
    printf("\n");
    return 0;
}
