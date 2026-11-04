import { Injectable } from '@nestjs/common';
import { Pinecone, Index } from '@pinecone-database/pinecone';

type GuidelinesMetadata = {
  docId: string;
  audience: string;
  diseaseTitle: string;
  text: string;
};

@Injectable()
export class GuidelineDBService {
  private readonly pc = new Pinecone(); // reads PINECONE_API_KEY
  private GuidelineIndexPromise?: Promise<Index<GuidelinesMetadata>>;

  private getGuidelineIndex() {
    this.GuidelineIndexPromise ??= (async () => {
      await this.pc.indexes.create({
        name: 'guidelines-history',
        schema: {
          fields: {
            _values: { type: 'dense_vector', dimension: 384, metric: 'cosine' },
          },
        },
        deployment: {
          deploymentType: 'managed',
          cloud: 'aws',
          region: 'us-east-1',
        },
        waitUntilReady: true,
        suppressConflicts: true,
      });
      const { host } = await this.pc.indexes.describe('guidelines-history');
      return this.pc.index<GuidelinesMetadata>({ host });
    })();
    return this.GuidelineIndexPromise;
  }

  async upsertGuidelines(
    guidelines: (GuidelinesMetadata & { embedding: number[] })[],
  ) {
    const index = await this.getGuidelineIndex();
    for (let i = 0; i < guidelines.length; i += 100) {
      // batches of 100
      await index.upsert({
        records: guidelines.slice(i, i + 100).map((v) => ({
          id: `${v.diseaseTitle}-${v.docId}`, // stable ID: re-ingest overwrites, no duplicates
          values: v.embedding,
          metadata: {
            diseaseTitle: v.diseaseTitle,
            audience: v.audience,
            text: v.text,
            docId: v.docId,
          },
        })),
      });
    }
  }

  async search(vector: number[], topK = 5, diseaseTitle?: string) {
    const index = await this.getGuidelineIndex();
    const res = await index.query({
      vector,
      topK,
      includeMetadata: true,
      ...(diseaseTitle && { filter: { diseaseTitle: { $eq: diseaseTitle } } }),
    });
    return res.matches;
  }
}
