#include <stdio.h>

int main(void) {
    int total = 0;
    int i;
    for (i = 0; i < 5; i++) {
        total += i;
        if (total > 5) goto done;
    }
done:
    printf("total = %d\n", total);
    return 0;
}
