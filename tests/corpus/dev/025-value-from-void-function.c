#include <stdio.h>

void show_table(int n) {
    int i;
    for (i = 1; i <= n; i++) {
        printf("%d x 7 = %d\n", i, i * 7);
    }
    return 0;
}

int main(void) {
    show_table(5);
    return 0;
}
