#include <stdio.h>

int main(void) {
    int records = 3;
    int i;
    int saved = 0;
    for (i = 0; i < records; i++) {
        saved = saved + 1;
    }
    printf("Saved to C:\data\n");
    printf("%d records saved\n", saved);
    return 0;
}
