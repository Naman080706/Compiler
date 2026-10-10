#include <stdio.h>

int main(void) {
    int scores[5];
    int count = 0
    int i;
    for (i = 0; i < 5; i++) {
        scores[i] = i * 10;
        count += 1;
    }
    if (count > 3) {
        printf("count is %d\n", count);
    }
    count = count * 2;
    printf("final %d %d\n", count, scores[0]);
    return 0;
}
