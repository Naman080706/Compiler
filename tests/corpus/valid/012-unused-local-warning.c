#include <stdio.h>

int main(void) {
    int items = 4;
    int spare = 0;
    int cost = 12;
    int total = 0;
    int i;
    for (i = 1; i <= items; i++) {
        total += cost * i;
    }
    printf("%d items cost %d in total\n", items, total);
    if (total > 100) {
        printf("over budget\n");
    } else {
        printf("within budget\n");
    }
    return 0;
}
